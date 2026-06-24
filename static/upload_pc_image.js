/**
 * PC 端图片上传增强：剪贴板粘贴、选屏截图。
 * 通过 window.UploadPcImage 暴露，供 register_daily / register_upload 复用。
 */
(function (global) {
  "use strict";

  function isDesktopUploadEnv() {
    const ua = navigator.userAgent || "";
    if (/Android|iPhone|iPod/i.test(ua)) return false;
    if (/iPad/i.test(ua)) return false;
    if (global.matchMedia && global.matchMedia("(max-width: 767px) and (pointer: coarse)").matches) {
      return false;
    }
    return true;
  }

  function supportsClipboardPaste() {
    return typeof global.ClipboardEvent !== "undefined";
  }

  function supportsDisplayCapture() {
    return !!(
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getDisplayMedia === "function"
    );
  }

  function extractImageFromClipboard(event) {
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) return null;
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const blob = item.getAsFile();
        if (!blob) continue;
        const ext = item.type.includes("png") ? "png" : "jpg";
        return new File([blob], `paste-${Date.now()}.${ext}`, { type: blob.type || item.type });
      }
    }
    return null;
  }

  function waitForVideoFrame(video) {
    return new Promise((resolve, reject) => {
      if (video.readyState >= 2 && video.videoWidth > 0) {
        resolve();
        return;
      }
      const onReady = () => {
        cleanup();
        if (video.videoWidth > 0) resolve();
        else reject(new Error("无法读取屏幕画面"));
      };
      const onError = () => {
        cleanup();
        reject(new Error("无法读取屏幕画面"));
      };
      const cleanup = () => {
        video.removeEventListener("loadeddata", onReady);
        video.removeEventListener("error", onError);
      };
      video.addEventListener("loadeddata", onReady);
      video.addEventListener("error", onError);
      setTimeout(() => {
        if (video.videoWidth > 0) {
          cleanup();
          resolve();
        }
      }, 500);
    });
  }

  async function captureScreenToFile() {
    if (!supportsDisplayCapture()) {
      throw new Error("当前浏览器不支持截图上传");
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
    });
    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    try {
      await video.play();
      await waitForVideoFrame(video);
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("截图失败");
      ctx.drawImage(video, 0, 0);
      const blob = await new Promise((resolve, reject) => {
        canvas.toBlob(
          (result) => (result ? resolve(result) : reject(new Error("截图失败"))),
          "image/jpeg",
          0.92
        );
      });
      return new File([blob], `screenshot-${Date.now()}.jpg`, { type: "image/jpeg" });
    } finally {
      stream.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    }
  }

  function bindPasteUploadZone({ zoneEl, onFile, onError, canUpload }) {
    if (!zoneEl) return;

    zoneEl.addEventListener("click", () => zoneEl.focus());

    zoneEl.addEventListener("paste", async (event) => {
      event.preventDefault();
      if (typeof canUpload === "function" && !canUpload()) {
        if (onError) onError("已达上传上限");
        return;
      }
      const file = extractImageFromClipboard(event);
      if (!file) {
        if (onError) onError("剪贴板中没有图片，请先截图或复制图片");
        return;
      }
      try {
        await onFile(file);
      } catch (err) {
        if (onError) onError(err && err.message ? err.message : "上传失败");
      }
    });
  }

  function bindScreenCaptureButton({ btnEl, onFile, onError, canUpload }) {
    if (!btnEl) return;

    btnEl.addEventListener("click", async () => {
      if (typeof canUpload === "function" && !canUpload()) {
        if (onError) onError("已达上传上限");
        return;
      }
      try {
        const file = await captureScreenToFile();
        await onFile(file);
      } catch (err) {
        if (!onError) return;
        if (err && (err.name === "NotAllowedError" || err.name === "AbortError")) {
          onError("已取消截图");
          return;
        }
        onError(err && err.message ? err.message : "截图失败");
      }
    });
  }

  function initPcImageUpload({ pasteZoneEl, captureBtnEl, onFile, onError, canUpload }) {
    if (!isDesktopUploadEnv()) return;

    if (supportsClipboardPaste() && pasteZoneEl) {
      pasteZoneEl.hidden = false;
      bindPasteUploadZone({ zoneEl: pasteZoneEl, onFile, onError, canUpload });
    } else if (pasteZoneEl) {
      pasteZoneEl.hidden = true;
    }

    if (captureBtnEl) {
      captureBtnEl.hidden = true;
    }
  }

  global.UploadPcImage = {
    isDesktopUploadEnv,
    supportsClipboardPaste,
    supportsDisplayCapture,
    extractImageFromClipboard,
    captureScreenToFile,
    bindPasteUploadZone,
    bindScreenCaptureButton,
    initPcImageUpload,
  };
})(window);
