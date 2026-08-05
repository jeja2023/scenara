import { ref, type Ref } from "vue";

import { apiBlob, blobToDataUrl } from "../api";

function revokeObjectUrl(value: string): void {
  if (value.startsWith("blob:")) URL.revokeObjectURL(value);
}

export function useMediaPreview(file: Ref<File | null>) {
  const mediaUrl = ref("");
  const serverPreviewUrl = ref("");
  const streamPreviewUrl = ref("");
  const fileDataUrl = ref("");
  const videoPlaybackFailed = ref(false);

  function clearMediaUrl(): void {
    revokeObjectUrl(mediaUrl.value);
    revokeObjectUrl(serverPreviewUrl.value);
    revokeObjectUrl(streamPreviewUrl.value);
    mediaUrl.value = "";
    serverPreviewUrl.value = "";
    streamPreviewUrl.value = "";
    fileDataUrl.value = "";
    videoPlaybackFailed.value = false;
  }

  async function handleImageError(): Promise<void> {
    if (!file.value || fileDataUrl.value) return;
    revokeObjectUrl(serverPreviewUrl.value);
    serverPreviewUrl.value = "";
    try {
      fileDataUrl.value = await blobToDataUrl(file.value);
      mediaUrl.value = fileDataUrl.value;
    } catch {
      // 即使文件无法解码，解析器仍会返回有用的校验错误。
    }
  }

  function handleVideoError(): void {
    videoPlaybackFailed.value = true;
  }

  async function loadServerPreview(
    assetId: string | null | undefined,
  ): Promise<void> {
    if (!assetId) return;
    try {
      const blob = await apiBlob(
        `/api/v1/media/assets/${encodeURIComponent(assetId)}/preview`,
      );
      const dataUrl = await blobToDataUrl(blob);
      revokeObjectUrl(serverPreviewUrl.value);
      serverPreviewUrl.value = dataUrl;
    } catch {
      // 预览生成属于尽力而为，解析和结果渲染仍可继续使用。
    }
  }

  async function loadStreamPreview(sourceId: string): Promise<void> {
    if (!sourceId) {
      revokeObjectUrl(streamPreviewUrl.value);
      streamPreviewUrl.value = "";
      return;
    }
    try {
      const blob = await apiBlob(
        `/api/v1/media/sources/${encodeURIComponent(sourceId)}/preview`,
      );
      const dataUrl = await blobToDataUrl(blob);
      revokeObjectUrl(streamPreviewUrl.value);
      streamPreviewUrl.value = dataUrl;
    } catch {
      revokeObjectUrl(streamPreviewUrl.value);
      streamPreviewUrl.value = "";
    }
  }

  return {
    mediaUrl,
    serverPreviewUrl,
    streamPreviewUrl,
    fileDataUrl,
    videoPlaybackFailed,
    clearMediaUrl,
    handleImageError,
    handleVideoError,
    loadServerPreview,
    loadStreamPreview,
  };
}
