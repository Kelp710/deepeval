from typing import List, Optional
from dataclasses import dataclass
from rich.console import Console
import json
import csv
import webbrowser
import os
import datetime

from deepeval.metrics import BaseMetric
from deepeval.api import Api, Endpoints
from deepeval.dataset.utils import (
    convert_test_cases_to_goldens,
    convert_goldens_to_test_cases,
)
from deepeval.dataset.api import (
    APIDataset,
    CreateDatasetHttpResponse,
    DatasetHttpResponse,
)
from deepeval.dataset.golden import Golden
from deepeval.test_case import LLMTestCase
from deepeval.utils import is_confident
from deepeval.synthesizer.base_synthesizer import BaseSynthesizer

valid_file_types = ["csv", "json"]


@dataclass
class EvaluationDataset:
    test_cases: List[LLMTestCase]
    goldens: List[Golden]

    def __init__(
        self,
        alias: Optional[str] = None,
        goldens: Optional[List[Golden]] = None,
        test_cases: Optional[List[LLMTestCase]] = None,
    ):
        if test_cases is not None:
            for test_case in test_cases:
                # TODO: refactor
                if not isinstance(test_case, LLMTestCase):
                    raise TypeError(
                        "Provided `test_cases` must be of type 'List[LLMTestCase]'."
                    )

                test_case.dataset_alias = alias
            self.test_cases = test_cases
        else:
            self.test_cases = []
        self.goldens = goldens or []
        self.alias = alias

    def add_test_case(self, test_case: LLMTestCase):
        # TODO: refactor
        if not isinstance(test_case, LLMTestCase):
            raise TypeError(
                "Provided `test_cases` must be of type 'List[LLMTestCase]'."
            )

        self.test_cases.append(test_case)

    def __iter__(self):
        return iter(self.test_cases)

    def evaluate(self, metrics: List[BaseMetric]):
        from deepeval import evaluate

        if len(self.test_cases) == 0:
            raise ValueError(
                "No test cases found in evaluation dataset. Unable to evaluate empty dataset."
            )

        return evaluate(self.test_cases, metrics)

    def add_test_cases_from_csv_file(
        self,
        file_path: str,
        input_col_name: str,
        actual_output_col_name: str,
        expected_output_col_name: Optional[str] = None,
        context_col_name: Optional[str] = None,
        context_col_delimiter: str = ";",
    ):
        """
        Load test cases from a CSV file.

        This method reads a CSV file, extracting test case data based on specified column names. It creates LLMTestCase objects for each row in the CSV and adds them to the Dataset instance. The context data, if provided, is expected to be a delimited string in the CSV, which this method will parse into a list.

        Args:
            file_path (str): Path to the CSV file containing the test cases.
            input_col_name (str): The column name in the CSV corresponding to the input for the test case.
            actual_output_col_name (str): The column name in the CSV corresponding to the actual output for the test case.
            expected_output_col_name (str, optional): The column name in the CSV corresponding to the expected output for the test case. Defaults to None.
            context_col_name (str, optional): The column name in the CSV corresponding to the context for the test case. Defaults to None.
            context_delimiter (str, optional): The delimiter used to separate items in the context list within the CSV file. Defaults to ';'.

        Returns:
            None: The method adds test cases to the Dataset instance but does not return anything.

        Raises:
            FileNotFoundError: If the CSV file specified by `file_path` cannot be found.
            pd.errors.EmptyDataError: If the CSV file is empty.
            KeyError: If one or more specified columns are not found in the CSV file.

        Note:
            The CSV file is expected to contain columns as specified in the arguments. Each row in the file represents a single test case. The method assumes the file is properly formatted and the specified columns exist. For context data represented as lists in the CSV, ensure the correct delimiter is specified.
        """
        try:
            import pandas as pd
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Please install pandas to use this method. 'pip install pandas'"
            )

        def get_column_data(df: pd.DataFrame, col_name: str, default=None):
            return (
                df[col_name].values
                if col_name in df.columns
                else [default] * len(df)
            )

        df = pd.read_csv(file_path)

        inputs = get_column_data(df, input_col_name)
        actual_outputs = get_column_data(df, actual_output_col_name)
        expected_outputs = get_column_data(
            df, expected_output_col_name, default=None
        )
        contexts = [
            context.split(context_col_delimiter) if context else []
            for context in get_column_data(df, context_col_name, default="")
        ]

        for input, actual_output, expected_output, context in zip(
            inputs, actual_outputs, expected_outputs, contexts
        ):
            self.add_test_case(
                LLMTestCase(
                    input=input,
                    actual_output=actual_output,
                    expected_output=expected_output,
                    context=context,
                    dataset_alias=self.alias,
                )
            )

    def add_test_cases_from_json_file(
        self,
        file_path: str,
        input_key_name: str,
        actual_output_key_name: str,
        expected_output_key_name: Optional[str] = None,
        context_key_name: Optional[str] = None,
    ):
        """
        Load test cases from a JSON file.

        This method reads a JSON file containing a list of objects, each representing a test case. It extracts the necessary information based on specified key names and creates LLMTestCase objects to add to the Dataset instance.

        Args:
            file_path (str): Path to the JSON file containing the test cases.
            input_key_name (str): The key name in the JSON objects corresponding to the input for the test case.
            actual_output_key_name (str): The key name in the JSON objects corresponding to the actual output for the test case.
            expected_output_key_name (str, optional): The key name in the JSON objects corresponding to the expected output for the test case. Defaults to None.
            context_key_name (str, optional): The key name in the JSON objects corresponding to the context for the test case. Defaults to None.

        Returns:
            None: The method adds test cases to the Dataset instance but does not return anything.

        Raises:
            FileNotFoundError: If the JSON file specified by `file_path` cannot be found.
            ValueError: If the JSON file is not valid or if required keys (input and actual output) are missing in one or more JSON objects.

        Note:
            The JSON file should be structured as a list of objects, with each object containing the required keys. The method assumes the file format and keys are correctly defined and present.
        """
        try:
            with open(file_path, "r") as file:
                json_list = json.load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"The file {file_path} was not found.")
        except json.JSONDecodeError:
            raise ValueError(f"The file {file_path} is not a valid JSON file.")

        # Process each JSON object
        for json_obj in json_list:
            if (
                input_key_name not in json_obj
                or actual_output_key_name not in json_obj
            ):
                raise ValueError(
                    "Required fields are missing in one or more JSON objects"
                )

            input = json_obj[input_key_name]
            actual_output = json_obj[actual_output_key_name]
            expected_output = json_obj.get(expected_output_key_name)
            context = json_obj.get(context_key_name)

            self.add_test_case(
                LLMTestCase(
                    input=input,
                    actual_output=actual_output,
                    expected_output=expected_output,
                    context=context,
                    dataset_alias=self.alias,
                )
            )

    def add_test_cases_from_hf_dataset(
        self,
        dataset_name: str,
        input_field_name: str,
        actual_output_field_name: str,
        expected_output_field_name: Optional[str] = None,
        context_field_name: Optional[str] = None,
        split: str = "train",
    ):
        """
        Load test cases from a Hugging Face dataset.

        This method loads a specified dataset and split from Hugging Face's datasets library, then iterates through each entry to create and add LLMTestCase objects to the Dataset instance based on specified field names.

        Args:
            dataset_name (str): The name of the Hugging Face dataset to load.
            split (str): The split of the dataset to load (e.g., 'train', 'test', 'validation'). Defaults to 'train'.
            input_field_name (str): The field name in the dataset corresponding to the input for the test case.
            actual_output_field_name (str): The field name in the dataset corresponding to the actual output for the test case.
            expected_output_field_name (str, optional): The field name in the dataset corresponding to the expected output for the test case. Defaults to None.
            context_field_name (str, optional): The field name in the dataset corresponding to the context for the test case. Defaults to None.

        Returns:
            None: The method adds test cases to the Dataset instance but does not return anything.

        Raises:
            ValueError: If the required fields (input and actual output) are not found in the dataset.
            FileNotFoundError: If the specified dataset is not available in Hugging Face's datasets library.
            datasets.DatasetNotFoundError: Specific Hugging Face error if the dataset or split is not found.
            json.JSONDecodeError: If there is an issue in reading or processing the dataset.

        Note:
            Ensure that the dataset structure aligns with the expected field names. The method assumes each dataset entry is a dictionary-like object.
        """

        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError(
                "The 'datasets' library is missing. Please install it using pip: pip install datasets"
            )
        hf_dataset = load_dataset(dataset_name, split=split)

        # Process each entry in the dataset
        for entry in hf_dataset:
            if (
                input_field_name not in entry
                or actual_output_field_name not in entry
            ):
                raise ValueError(
                    "Required fields are missing in one or more dataset entries"
                )

            input = entry[input_field_name]
            actual_output = entry[actual_output_field_name]
            expected_output = entry.get(expected_output_field_name)
            context = entry.get(context_field_name)

            self.add_test_case(
                LLMTestCase(
                    input=input,
                    actual_output=actual_output,
                    expected_output=expected_output,
                    context=context,
                    dataset_alias=self.alias,
                )
            )

    def push(self, alias: str):
        if len(self.test_cases) == 0 and len(self.goldens) == 0:
            raise ValueError(
                "Unable to push empty dataset to Confident AI, there must be at least one test case or golden in dataset"
            )
        if is_confident():
            goldens = self.goldens
            goldens.extend(convert_test_cases_to_goldens(self.test_cases))
            api_dataset = APIDataset(
                alias=alias, overwrite=False, goldens=goldens
            )
            try:
                body = api_dataset.model_dump(by_alias=True, exclude_none=True)
            except AttributeError:
                # Pydantic version below 2.0
                body = api_dataset.dict(by_alias=True, exclude_none=True)
            api = Api()
            result = api.post_request(
                endpoint=Endpoints.DATASET_ENDPOINT.value,
                body=body,
            )
            if result:
                response = CreateDatasetHttpResponse(
                    link=result["link"],
                )
                link = response.link
                console = Console()
                console.print(
                    "✅ Dataset successfully pushed to Confidnet AI! View at "
                    f"[link={link}]{link}[/link]"
                )
                webbrowser.open(link)
        else:
            raise Exception(
                "To push dataset to Confident AI, run `deepeval login`"
            )

    def pull(self, alias: str, auto_convert_goldens_to_test_cases: bool = True):
        if is_confident():
            self.alias = alias
            api = Api()
            result = api.get_request(
                endpoint=Endpoints.DATASET_ENDPOINT.value,
                params={"alias": alias},
            )

            response = DatasetHttpResponse(
                goldens=result["goldens"],
            )

            if auto_convert_goldens_to_test_cases:
                self.test_cases = convert_goldens_to_test_cases(
                    response.goldens, alias
                )
        else:
            raise Exception(
                "Run `deepeval login` to pull dataset from Confident AI"
            )

    def generate_goldens(
        self,
        synthesizer: BaseSynthesizer,
        contexts: List[List[str]],
        max_goldens_per_context: int = 2,
    ):
        self.goldens.extend(
            synthesizer.generate_goldens(contexts, max_goldens_per_context)
        )

    # TODO: add save test cases as well
    def save_as(self, file_type: str, directory: str):
        if file_type not in valid_file_types:
            raise ValueError(
                f"Invalid file type. Available file types to save as: {', '.join(type for type in valid_file_types)}"
            )

        if len(self.goldens) == 0:
            raise ValueError(
                f"No synthetic goldens found. Please generate goldens before attempting to save data as {file_type}"
            )

        new_filename = (
            datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + f".{file_type}"
        )

        if not os.path.exists(directory):
            os.makedirs(directory)

        full_file_path = os.path.join(directory, new_filename)

        if file_type == "json":
            with open(full_file_path, "w") as file:
                json_data = [
                    {
                        "input": golden.input,
                        "actual_output": golden.actual_output,
                        "expected_output": golden.expected_output,
                        "context": golden.context,
                    }
                    for golden in self.goldens
                ]
                json.dump(json_data, file, indent=4)

        elif file_type == "csv":
            with open(full_file_path, "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(
                    ["input", "actual_output", "expected_output", "context"]
                )
                for golden in self.goldens:
                    context_str = "|".join(golden.context)
                    writer.writerow(
                        [
                            golden.input,
                            golden.actual_output,
                            golden.expected_output,
                            context_str,
                        ]
                    )

        print(f"Evaluation dataset saved at {full_file_path}!")
