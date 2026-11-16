"""PyQt6 主視窗與控制面板。"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import config
from core.camera import CameraWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("瞬間移動 · 攝影機特效工具")
        self.resize(1080, 640)

        self._worker = CameraWorker()
        self._camera_running = False
        self._countdown_remaining = -1
        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._countdown_tick)

        self._build_ui()
        self._connect_signals()
        self._update_controls(False)

    # ------------------------------------------------------------------ #
    # 介面建立
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        self.video_label = QLabel("尚未啟動攝影機")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet(
            "background: #1a1a1a; color: #888; border: 1px solid #333;"
        )
        self.video_label.setSizePolicy(
            self.video_label.sizePolicy().horizontalPolicy(),
            self.video_label.sizePolicy().verticalPolicy(),
        )

        right = QFrame()
        right.setMinimumWidth(320)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(10)

        right_layout.addWidget(self._camera_group())
        right_layout.addWidget(self._background_group())
        right_layout.addWidget(self._record_group())
        right_layout.addWidget(self._effect_group())
        right_layout.addWidget(self._status_group(), stretch=1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.video_label, stretch=1)
        layout.addWidget(right)
        self.setCentralWidget(central)

    def _group(self, title):
        box = QGroupBox(title)
        box.setLayout(QVBoxLayout())
        box.layout().setSpacing(6)
        return box

    def _camera_group(self):
        box = self._group("攝影機")
        row = QHBoxLayout()
        row.addWidget(QLabel("裝置編號："))
        self.spin_camera = QSpinBox()
        self.spin_camera.setRange(0, 10)
        self.spin_camera.setValue(0)
        row.addWidget(self.spin_camera)
        box.layout().addLayout(row)

        row = QHBoxLayout()
        self.btn_start = QPushButton("啟動攝影機")
        self.btn_stop = QPushButton("停止攝影機")
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        box.layout().addLayout(row)
        return box

    def _background_group(self):
        box = self._group("空景圖（倒數自動拍攝）")
        row = QHBoxLayout()
        row.addWidget(QLabel("倒數秒數："))
        self.spin_countdown = QSpinBox()
        self.spin_countdown.setRange(1, 60)
        self.spin_countdown.setValue(config.DEFAULT_COUNTDOWN)
        row.addWidget(self.spin_countdown)
        row.addStretch(1)
        box.layout().addLayout(row)

        self.btn_capture_bg = QPushButton("拍攝空景圖")
        box.layout().addWidget(self.btn_capture_bg)

        self.background_thumb = QLabel("尚未拍攝空景圖")
        self.background_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.background_thumb.setMinimumHeight(90)
        self.background_thumb.setStyleSheet(
            "background: #222; color: #888; border: 1px dashed #555;"
        )
        self._background_pixmap = None
        box.layout().addWidget(self.background_thumb)
        return box

    def _record_group(self):
        box = self._group("錄影（輸出 MP4）")
        self.btn_record = QPushButton("開始錄影")
        self.btn_record.setCheckable(True)
        box.layout().addWidget(self.btn_record)

        self.label_record = QLabel("未錄影 · 輸出資料夾：captures/")
        self.label_record.setWordWrap(True)
        box.layout().addWidget(self.label_record)
        return box

    def _effect_group(self):
        box = self._group("特效")
        self.effect_list = QListWidget()
        self.effect_list.addItems(config.EFFECTS)
        self.effect_list.setCurrentRow(0)
        self.effect_list.setMaximumHeight(80)
        box.layout().addWidget(self.effect_list)

        self.chk_effect = QCheckBox("啟用特效")
        box.layout().addWidget(self.chk_effect)

        row = QHBoxLayout()
        row.addWidget(QLabel("消散秒數："))
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.5, 15.0)
        self.spin_duration.setSingleStep(0.5)
        self.spin_duration.setValue(config.DEFAULT_TELEPORT_DURATION)
        row.addWidget(self.spin_duration)
        box.layout().addLayout(row)

        hint = QLabel("手勢：食指與中指併攏，指向額頭眉心")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; font-size: 11px;")
        box.layout().addWidget(hint)

        self.btn_reset = QPushButton("重置人物")
        box.layout().addWidget(self.btn_reset)
        return box

    def _status_group(self):
        box = self._group("狀態")
        row = QHBoxLayout()
        self.gesture_dot = QLabel("●")
        self.gesture_dot.setStyleSheet("color: #555; font-size: 18px;")
        self.label_gesture = QLabel("未偵測到手勢")
        row.addWidget(self.gesture_dot)
        row.addWidget(self.label_gesture)
        box.layout().addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("特效進度："))
        self.label_effect_state = QLabel("未啟用")
        row.addWidget(self.label_effect_state)
        row.addStretch(1)
        box.layout().addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        box.layout().addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        box.layout().addWidget(self.log)
        return box

    # ------------------------------------------------------------------ #
    # 訊號連接
    # ------------------------------------------------------------------ #
    def _connect_signals(self):
        self.btn_start.clicked.connect(self._start_camera)
        self.btn_stop.clicked.connect(self._stop_camera)
        self.btn_capture_bg.clicked.connect(self._capture_background)
        self.btn_record.toggled.connect(self._toggle_record)
        self.btn_reset.clicked.connect(self._reset_effect)
        self.chk_effect.toggled.connect(self._toggle_effect)
        self.effect_list.currentRowChanged.connect(self._on_effect_selected)
        self.spin_duration.valueChanged.connect(
            lambda v: self._worker.set_teleport_duration(v)
        )

        self._worker.frame_ready.connect(self._on_frame)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.info.connect(self._log)
        self._worker.background_saved.connect(self._on_background_saved)
        self._worker.recording_changed.connect(self._on_recording_changed)
        self._worker.gesture_changed.connect(self._on_gesture)
        self._worker.effect_progress.connect(self._on_effect_progress)

    # ------------------------------------------------------------------ #
    # 控制事件
    # ------------------------------------------------------------------ #
    def _start_camera(self):
        self._worker.start_camera(self.spin_camera.value())
        self._camera_running = True
        self._update_controls(True)
        self._log("正在啟動攝影機…")

    def _stop_camera(self):
        if self.btn_record.isChecked():
            self.btn_record.setChecked(False)
        self._worker.stop_camera()
        self._camera_running = False
        self._countdown_timer.stop()
        self._countdown_remaining = -1
        self._update_controls(False)
        self.video_label.setText("攝影機已停止")
        self.video_label.setPixmap(QPixmap())

    def _capture_background(self):
        if not self._camera_running:
            QMessageBox.warning(self, "尚未啟動", "請先啟動攝影機。")
            return
        self._countdown_remaining = self.spin_countdown.value()
        self.btn_capture_bg.setEnabled(False)
        self._countdown_timer.start(1000)
        self._log(f"空景倒數開始：{self._countdown_remaining} 秒（請離開畫面）")

    def _countdown_tick(self):
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._countdown_remaining = -1
            self.btn_capture_bg.setEnabled(True)
            self._worker.request_background()
        else:
            self._log(f"倒數 {self._countdown_remaining} 秒…")

    def _toggle_record(self, checked):
        if not self._camera_running:
            self.btn_record.setChecked(False)
            return
        if checked:
            self._worker.start_recording()
        else:
            self._worker.stop_recording()

    def _toggle_effect(self, checked):
        self._worker.set_effect_enabled(checked)
        if checked:
            name = self.effect_list.currentItem()
            if name is None:
                self.effect_list.setCurrentRow(0)
                name = self.effect_list.currentItem()
            self._worker.set_effect(name.text() if name else None)
            self._worker.reset_effect()
            self._log(f"已啟用特效：{name.text() if name else '無'}")
        else:
            self._log("特效已停用")

    def _on_effect_selected(self, row):
        if row < 0 or not self.chk_effect.isChecked():
            return
        name = self.effect_list.item(row).text()
        self._worker.set_effect(name)
        self._worker.reset_effect()
        self._log(f"已切換特效：{name}")

    def _reset_effect(self):
        self._worker.reset_effect()

    # ------------------------------------------------------------------ #
    # 背景執行緒訊號處理
    # ------------------------------------------------------------------ #
    def _on_frame(self, qimage):
        if self._countdown_remaining > 0:
            painter = QPainter(qimage)
            painter.fillRect(qimage.rect(), QColor(0, 0, 0, 110))
            font = QFont()
            font.setPointSize(72)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                qimage.rect(), Qt.AlignmentFlag.AlignCenter,
                str(self._countdown_remaining),
            )
            painter.end()

        pixmap = QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)

    def _on_background_saved(self, path, thumb):
        self._background_pixmap = QPixmap.fromImage(thumb)
        scaled = self._background_pixmap.scaled(
            self.background_thumb.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.background_thumb.setPixmap(scaled)
        self._log(f"空景圖已儲存：{path}")

    def _on_recording_changed(self, recording, path):
        if recording:
            self.label_record.setText(f"● 錄影中 → {path}")
            self.label_record.setStyleSheet("color: #ff6b6b;")
        else:
            self.label_record.setText(f"未錄影 · 輸出資料夾：captures/")
            self.label_record.setStyleSheet("")

    def _on_gesture(self, detected):
        if detected:
            self.gesture_dot.setStyleSheet("color: #4caf50; font-size: 18px;")
            self.label_gesture.setText("偵測到傳送手勢！")
        else:
            self.gesture_dot.setStyleSheet("color: #555; font-size: 18px;")
            self.label_gesture.setText("未偵測到手勢")

    def _on_effect_progress(self, percent, state):
        self.progress.setValue(percent)
        self.label_effect_state.setText(state)

    def _on_error(self, message):
        self._log(f"錯誤：{message}")
        QMessageBox.critical(self, "錯誤", message)
        if not self._camera_running:
            self._update_controls(False)

    def _log(self, message):
        self.log.append(message)

    def _update_controls(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.spin_camera.setEnabled(not running)
        self.btn_capture_bg.setEnabled(running)
        self.btn_record.setEnabled(running)
        self.chk_effect.setEnabled(running)
        self.effect_list.setEnabled(running)
        self.spin_duration.setEnabled(running)
        self.btn_reset.setEnabled(running)

    # ------------------------------------------------------------------ #
    def closeEvent(self, event):
        self._countdown_timer.stop()
        if self._camera_running:
            self._stop_camera()
        super().closeEvent(event)
