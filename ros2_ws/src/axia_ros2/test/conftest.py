import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))                      # axia_ros2 from the source tree
sys.path.insert(0, str(root.parents[2]))           # the repository (AxiaDriver)
