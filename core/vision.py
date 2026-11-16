"""影像辨識：以 MediaPipe Tasks 進行人物分割與手勢偵測。"""
import math

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import numpy as np

from . import config


class VisionEngine:
    """封裝 MediaPipe 的 HandLandmarker 與 ImageSegmenter。

    對外提供 process()：輸入 BGR 影格，回傳人物遮罩、是否符合傳送手勢、
    以及手勢位置與額頭位置（供介面顯示除錯用）。
    """

    def __init__(self):
        hand_options = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(config.HAND_MODEL)
            ),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._hands = mp_vision.HandLandmarker.create_from_options(hand_options)

        segmenter_options = mp_vision.ImageSegmenterOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(config.SEGMENTER_MODEL)
            ),
            running_mode=mp_vision.RunningMode.VIDEO,
            output_confidence_masks=True,
        )
        self._segmenter = mp_vision.ImageSegmenter.create_from_options(
            segmenter_options
        )

        self._timestamp = 0  # 遞增時間戳（毫秒），MediaPipe 要求嚴格遞增

    def close(self):
        self._hands.close()
        self._segmenter.close()

    def process(self, frame_bgr):
        """處理單一影格。

        Returns:
            mask: float32 (h, w)，0=背景、1=人物
            gesture: bool，是否符合「雙指併攏指向額頭」手勢
            tip_point: (x, y) 指尖中點座標（像素），或 None
            forehead_point: (x, y) 額頭估計位置（像素），或 None
        """
        h, w = frame_bgr.shape[:2]
        self._timestamp += 33
        ts = self._timestamp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # 人物遮罩
        mask = np.zeros((h, w), dtype=np.float32)
        try:
            seg_result = self._segmenter.segment_for_video(mp_image, ts)
            if seg_result.confidence_masks:
                mask = seg_result.confidence_masks[0].numpy_view()
                if mask.ndim == 3:
                    mask = mask[..., 0]
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
                mask = np.clip(mask, 0.0, 1.0).astype(np.float32)
        except Exception:
            pass

        # 手部關鍵點
        gesture = False
        tip_point = None
        forehead_point = self._find_forehead(mask, w, h)
        try:
            hand_result = self._hands.detect_for_video(mp_image, ts)
            for landmarks in hand_result.hand_landmarks:
                ok, tip = self._is_teleport_gesture(
                    landmarks, w, h, forehead_point
                )
                if ok:
                    gesture = True
                    tip_point = tip
                    break
        except Exception:
            pass

        return mask, gesture, tip_point, forehead_point

    # ------------------------------------------------------------------ #
    # 內部方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_forehead(mask, w, h):
        """由人物遮罩估計額頭位置（人物區域頂端往下一點、水平中心）。"""
        binary = (mask > 0.5).astype(np.uint8)
        ys, xs = np.where(binary)
        if len(ys) == 0:
            return None

        top = int(ys.min())
        band_bottom = min(h, top + max(1, int(0.18 * h)))
        band = binary[top:band_bottom]
        cols = np.where(band.any(axis=0))[0]
        if len(cols) == 0:
            return None

        cx = int((int(cols.min()) + int(cols.max())) / 2)
        cy = min(h - 1, top + max(1, int(0.05 * h)))
        return (cx, cy)

    @staticmethod
    def _is_teleport_gesture(landmarks, w, h, forehead_point):
        """判斷是否為「食指與中指併攏指向額頭」的手勢。"""
        def point(i):
            lm = landmarks[i]
            return (lm.x * w, lm.y * h)

        def dist(a, b):
            return math.hypot(a[0] - b[0], a[1] - b[1])

        wrist = point(0)
        middle_mcp = point(9)
        hand_scale = dist(wrist, middle_mcp)
        if hand_scale < 1e-3:
            return False, None

        index_tip, index_pip = point(8), point(6)
        middle_tip, middle_pip = point(12), point(10)
        ring_tip, ring_pip = point(16), point(14)
        pinky_tip, pinky_pip = point(20), point(18)

        # 食指、中指需伸直
        index_extended = dist(index_tip, wrist) > dist(index_pip, wrist) * 1.15
        middle_extended = dist(middle_tip, wrist) > dist(middle_pip, wrist) * 1.15
        # 無名指、小指需彎曲
        ring_folded = dist(ring_tip, wrist) < dist(ring_pip, wrist) * 1.05
        pinky_folded = dist(pinky_tip, wrist) < dist(pinky_pip, wrist) * 1.05
        # 食指與中指需併攏
        fingers_together = (
            dist(index_tip, middle_tip) < hand_scale * config.FINGER_TOGETHHER_RATIO
        )

        if not (
            index_extended
            and middle_extended
            and ring_folded
            and pinky_folded
            and fingers_together
        ):
            return False, None

        # 指尖中點
        tip = (
            (index_tip[0] + middle_tip[0]) / 2.0,
            (index_tip[1] + middle_tip[1]) / 2.0,
        )

        # 需靠近額頭（同時以手掌尺寸與畫面比例限制，避免過度寬鬆）
        if forehead_point is not None:
            max_dist = min(
                hand_scale * config.FOREHEAD_NEAR_RATIO,
                h * config.FOREHEAD_NEAR_FRAME_RATIO,
            )
            if dist(tip, forehead_point) >= max_dist:
                return False, None

        return True, tip
