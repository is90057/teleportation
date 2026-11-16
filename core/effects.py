"""特效實作：星艦迷航風格的「瞬間移動」消散動畫。"""
import cv2
import numpy as np


def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class TeleportEffect:
    """以人物遮罩 + 空景圖，將人物逐漸分解為光點並消失。"""

    IDLE = "idle"
    ACTIVE = "active"
    DONE = "done"

    def __init__(self, duration=3.0):
        self.duration = max(0.5, float(duration))
        self.state = self.IDLE
        self.start_time = 0.0
        self._noise = None
        self._noise_shape = None

    def trigger(self, now):
        self.state = self.ACTIVE
        self.start_time = now
        self._noise = None

    def reset(self):
        self.state = self.IDLE
        self.start_time = 0.0
        self._noise = None

    def is_active(self):
        return self.state == self.ACTIVE

    def is_done(self):
        return self.state == self.DONE

    def progress(self, now):
        if self.state == self.IDLE:
            return 0.0
        if self.state == self.DONE:
            return 1.0
        return min(1.0, max(0.0, (now - self.start_time) / self.duration))

    def apply(self, frame, background, mask, now):
        """回傳套用特效後的 BGR 影格。"""
        if self.state == self.IDLE:
            return frame
        if background is None:
            return frame

        h, w = frame.shape[:2]
        bg = background
        if bg.shape[:2] != (h, w):
            bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
        if mask is None or mask.shape[:2] != (h, w):
            mask = np.zeros((h, w), dtype=np.float32)

        p = self.progress(now)
        if p >= 1.0:
            self.state = self.DONE
            return bg.copy()

        if self._noise is None or self._noise_shape != (h, w):
            # 平滑隨機場讓消散呈現不規則但成片的區塊，而非雜訊點
            coarse = cv2.GaussianBlur(
                np.random.rand(h, w).astype(np.float32), (0, 0), 12
            )
            self._noise = np.clip(coarse * 1.6, 0.0, 1.0)
            self._noise_shape = (h, w)

        # y_up：1 在畫面頂端、0 在底端 → 消散由下往上掃
        y_up = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None]
        y_down = 1.0 - y_up

        front = p * 1.3 - 0.15
        dissolve = (y_up + self._noise * 0.30) < front

        keep = mask * (~dissolve).astype(np.float32)
        keep *= 1.0 - _smoothstep(0.75, 1.0, p)
        alpha = keep[..., None]

        frame_f = frame.astype(np.float32)
        bg_f = bg.astype(np.float32)
        out = bg_f * (1.0 - alpha) + frame_f * alpha

        # 消散邊緣的青色閃動光帶
        band = np.exp(-(((y_up - front) / 0.06) ** 2))
        band *= 0.65 + 0.35 * np.sin(y_down * 120.0 + now * 25.0)
        band_mask = band * mask
        glow = np.zeros_like(out)  # BGR：青色 = 藍 + 綠
        glow[..., 0] = band_mask * 255
        glow[..., 1] = band_mask * 255
        glow[..., 2] = band_mask * 90

        # 人物中心的光柱
        beam_glow = np.zeros_like(out)
        ys, xs = np.where(mask > 0.6)
        if len(xs) > 0:
            cx = float(np.mean(xs))
            grid_x = np.arange(w, dtype=np.float32)[None, :]
            beam_x = np.exp(-(((grid_x - cx) / (w * 0.10)) ** 2))
            beam = beam_x * mask * (0.10 + 0.08 * np.sin(now * 12.0))
            beam *= (1.0 - p) ** 2
            beam_glow[..., 0] = beam * 255
            beam_glow[..., 1] = beam * 220
            beam_glow[..., 2] = beam * 60

        # 消散處的閃爍光點
        sparkles = np.zeros((h, w), dtype=np.float32)
        n = int(20 + 50 * p)
        sy = np.random.randint(0, h, n)
        sx = np.random.randint(0, w, n)
        if len(sy):
            valid = (mask[sy, sx] > 0.6) & (
                np.abs(y_up[sy, 0] - front) < 0.14
            )
            if valid.any():
                vals = np.random.rand(int(valid.sum())) * 0.7 + 0.3
                sparkles[sy[valid], sx[valid]] = vals
                sparkles = cv2.dilate(
                    sparkles, np.ones((3, 3), np.float32), iterations=1
                )
        sparkle_glow = np.zeros_like(out)
        sparkle_glow[..., 0] = sparkles * 255
        sparkle_glow[..., 1] = sparkles * 240
        sparkle_glow[..., 2] = sparkles * 170

        out = np.clip(out + glow + beam_glow + sparkle_glow, 0, 255)
        return out.astype(np.uint8)
