from abc import ABC, abstractmethod
from typing import Any, Optional, List


class DeepEvalBaseModel(ABC):
    def __init__(self, model_name: Optional[str] = None, *args, **kwargs):
        self.model_name = model_name
        self.model = self.load_model(*args, **kwargs)

    @abstractmethod
    def load_model(self, *args, **kwargs):
        """Loads a model, that will be responsible for scoring.

        Returns:
            A model object
        """
        pass

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._call(*args, **kwargs)

    @abstractmethod
    def _call(self, *args, **kwargs):
        """Runs the model to score / ourput the model predictions.

        Returns:
            A score or a list of results.
        """
        pass


class DeepEvalBaseLLM(ABC):
    def __init__(self, model_name: Optional[str] = None, *args, **kwargs):
        self.model_name = model_name
        self.model = self.load_model(*args, **kwargs)

    @abstractmethod
    def load_model(self, *args, **kwargs):
        """Loads a model, that will be responsible for scoring.

        Returns:
            A model object
        """
        pass

    @abstractmethod
    def generate(self, *args, **kwargs) -> str:
        """Runs the model to output LLM response.

        Returns:
            A string.
        """
        pass

    @abstractmethod
    async def a_generate(self, *args, **kwargs) -> str:
        """Runs the model to output LLM response.

        Returns:
            A string.
        """
        pass


class DeepEvalBaseEmbeddingModel(ABC):
    def __init__(self, model_name: Optional[str] = None, *args, **kwargs):
        self.model_name = model_name
        self.model = self.load_model(*args, **kwargs)

    @abstractmethod
    def load_model(self, *args, **kwargs):
        """Loads a model, that will be responsible for generating text embeddings.

        Returns:
            A model object
        """
        pass

    def __call__(self, *args: Any, **kwargs: Any) -> List[float]:
        return self._call(*args, **kwargs)

    @abstractmethod
    def _call(self, *args, **kwargs) -> List[float]:
        """Runs the model to generate text embeddings.

        Returns:
            A list of float.
        """
        pass
