import sys
from unittest.mock import MagicMock

# Mock grpc and its cython submodules
mock_grpc = MagicMock()
mock_grpc.__version__ = "1.60.0"
sys.modules['grpc'] = mock_grpc
sys.modules['grpc._cython'] = MagicMock()
sys.modules['grpc._cython.cygrpc'] = MagicMock()

try:
    import vertexai
    print("Imported vertexai successfully!")
    from vertexai._genai.types.common import EvaluationDataset
    print("Imported EvaluationDataset successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
