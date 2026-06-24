import sys
from unittest.mock import MagicMock

# Mock vertexai and its submodules
sys.modules['vertexai'] = MagicMock()
sys.modules['vertexai._genai'] = MagicMock()
sys.modules['vertexai._genai._evals_visualization'] = MagicMock()
sys.modules['google.cloud.aiplatform'] = MagicMock()
sys.modules['google.api_core'] = MagicMock()
sys.modules['grpc'] = MagicMock()

try:
    from google.agents.cli.main import main
    print("Import successful!")
    sys.argv = ['agents-cli', 'eval', 'grade', '--help']
    main()
except Exception as e:
    import traceback
    traceback.print_exc()
