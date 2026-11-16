"""全專案共用的常數設定。"""
from pathlib import Path

# 專案根目錄
ROOT = Path(__file__).resolve().parent.parent

# MediaPipe 模型檔案（隨專案提供，可離線使用）
MODELS_DIR = ROOT / "models"
HAND_MODEL = MODELS_DIR / "hand_landmarker.task"
SEGMENTER_MODEL = MODELS_DIR / "selfie_segmenter.tflite"

# 輸出資料夾
CAPTURES_DIR = ROOT / "captures"

# 攝影機預設解析度
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# 特效定義
EFFECT_TELEPORT = "瞬間移動"
EFFECTS = [EFFECT_TELEPORT]

# 特效預設消散時間（秒）
DEFAULT_TELEPORT_DURATION = 3.0

# 空景倒數預設秒數
DEFAULT_COUNTDOWN = 3

# 手勢判定：雙指指尖靠近的最大距離（相對於手掌尺寸）
FINGER_TOGETHHER_RATIO = 0.45

# 手勢判定：指尖靠近額頭的最大距離（相對於手掌尺寸）
FOREHEAD_NEAR_RATIO = 2.0

# 手勢判定：指尖靠近額頭的最大距離（相對於畫面高度）
FOREHEAD_NEAR_FRAME_RATIO = 0.22
