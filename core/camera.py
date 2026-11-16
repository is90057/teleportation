"""攝影機擷取、辨識、特效與錄影的背景執行緒。"""
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from . import config
from .effects import TeleportEffect
from .vision import VisionEngine


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class CameraWorker(QThread):
    """在背景持續讀取攝影機影格並完成所有影像處理。"""

    frame_ready = pyqtSignal(object)          # QImage
    error_occurred = pyqtSignal(str)
    background_saved = pyqtSignal(str, object)  # 檔案路徑, QImage 縮圖
    recording_changed = pyqtSignal(bool, str)   # 是否錄影中, 檔案路徑
    gesture_changed = pyqtSignal(bool)          # 是否偵測到手勢
    effect_progress = pyqtSignal(int, str)      # 百分比, 狀態文字
    info = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._running = False
        self._effect_enabled = False
        self._effect_name = None
        self._teleport_duration = config.DEFAULT_TELEPORT_DURATION
        self._capture_bg_requested = False
        self._record_requested = False
        self._stop_record_requested = False
        self._reset_requested = False
        self._writer = None
        self._record_path = ""
        self._cap = None
        self._vision = None

    # ------------------------------------------------------------------ #
    # 由主執行緒呼叫的控制方法
    # ------------------------------------------------------------------ #
    def start_camera(self, index=0):
        with self._lock:
            self._running = True
            self._camera_index = int(index)
        if not self.isRunning():
            self.start()

    def stop_camera(self):
        with self._lock:
            self._running = False
        self.wait(3000)

    def set_effect_enabled(self, enabled):
        with self._lock:
            self._effect_enabled = bool(enabled)
            if not enabled:
                self._effect_name = None

    def set_effect(self, name):
        with self._lock:
            self._effect_name = name

    def set_teleport_duration(self, seconds):
        with self._lock:
            self._teleport_duration = max(0.5, float(seconds))

    def request_background(self):
        with self._lock:
            self._capture_bg_requested = True

    def start_recording(self):
        with self._lock:
            self._record_requested = True

    def stop_recording(self):
        with self._lock:
            self._stop_record_requested = True

    def reset_effect(self):
        with self._lock:
            self._reset_requested = True

    # ------------------------------------------------------------------ #
    # 背景執行緒主迴圈
    # ------------------------------------------------------------------ #
    def run(self):
        config.CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

        self._cap = cv2.VideoCapture(self._camera_index)
        if not self._cap.isOpened():
            self.error_occurred.emit("無法開啟攝影機，請確認裝置是否連線或被其他程式佔用。")
            return

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)

        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or config.CAMERA_WIDTH
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or config.CAMERA_HEIGHT
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        if fps <= 0 or fps > 60:
            fps = 30.0

        try:
            self._vision = VisionEngine()
        except Exception as exc:
            self.error_occurred.emit(f"辨識模型載入失敗：{exc}")
            self._cap.release()
            return

        effect = TeleportEffect(config.DEFAULT_TELEPORT_DURATION)
        background = None
        self.info.emit(f"攝影機已啟動（{width} x {height}）")

        try:
            while self._running:
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    self.msleep(30)
                    continue

                # 取出並清除一次性請求
                with self._lock:
                    effect_enabled = self._effect_enabled
                    effect_name = self._effect_name
                    duration = self._teleport_duration
                    want_bg = self._capture_bg_requested
                    want_record = self._record_requested
                    want_stop_record = self._stop_record_requested
                    want_reset = self._reset_requested
                    self._capture_bg_requested = False
                    self._record_requested = False
                    self._stop_record_requested = False
                    self._reset_requested = False

                # 鏡像 flipping，操作手感較直覺
                frame = cv2.flip(frame, 1)

                if want_bg:
                    background = frame.copy()
                    path = config.CAPTURES_DIR / f"background_{_timestamp()}.png"
                    cv2.imwrite(str(path), background)
                    thumb = self._to_qimage(background)
                    self.background_saved.emit(str(path), thumb)
                    self.info.emit(f"空景圖已拍攝：{path.name}")

                if want_reset:
                    effect.reset()
                    self.info.emit("特效已重置，人物重新出現。")

                if abs(duration - effect.duration) > 1e-6:
                    effect.duration = duration

                use_effect = (
                    effect_enabled
                    and effect_name == config.EFFECT_TELEPORT
                    and background is not None
                )

                mask = None
                gesture = False
                now = time.monotonic()
                if use_effect:
                    mask, gesture, _, _ = self._vision.process(frame)
                    if gesture and effect.state == TeleportEffect.IDLE:
                        effect.trigger(now)
                        self.info.emit("偵測到傳送手勢，開始瞬間移動！")
                    output = effect.apply(frame, background, mask, now)
                    percent = int(effect.progress(now) * 100)
                    state_text = {
                        TeleportEffect.IDLE: "待機",
                        TeleportEffect.ACTIVE: "傳送中",
                        TeleportEffect.DONE: "已消失",
                    }[effect.state]
                    self.effect_progress.emit(percent, state_text)
                else:
                    output = frame
                    self.effect_progress.emit(0, "未啟用")

                self.gesture_changed.emit(gesture)

                # 錄影（寫入含特效的最終畫面）
                if want_record:
                    self._open_writer(width, height, fps)
                if want_stop_record:
                    self._close_writer()
                if self._writer is not None:
                    self._writer.write(output)

                self.frame_ready.emit(self._to_qimage(output))
        finally:
            self._close_writer()
            if self._vision is not None:
                self._vision.close()
            if self._cap is not None:
                self._cap.release()
            self.info.emit("攝影機已停止。")

    # ------------------------------------------------------------------ #
    # 輔助方法
    # ------------------------------------------------------------------ #
    def _open_writer(self, width, height, fps):
        if self._writer is not None:
            return
        path = config.CAPTURES_DIR / f"recording_{_timestamp()}.mp4"
        for codec in ("avc1", "mp4v"):
            writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height)
            )
            if writer.isOpened():
                self._writer = writer
                self._record_path = str(path)
                self.recording_changed.emit(True, str(path))
                self.info.emit(f"開始錄影：{path.name}")
                return
            writer.release()
        self.error_occurred.emit("無法建立 MP4 錄影檔（編解碼器不支援）。")

    def _close_writer(self):
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            self.recording_changed.emit(False, self._record_path)
            self.info.emit(f"錄影已儲存：{Path(self._record_path).name}")
            self._record_path = ""

    @staticmethod
    def _to_qimage(frame_bgr):
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
