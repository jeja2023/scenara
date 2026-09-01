import type { Ref } from "vue";
import { api } from "../../api";
import type { MediaMode } from "../../composables/useDomainCatalog";
import type { Domain, MediaAsset, MediaSource } from "../../types";

type InputOrigin = "library" | "upload";

interface ParseMediaInputOptions {
  assetId: Ref<string>;
  assets: Ref<MediaAsset[]>;
  clearMediaUrl: () => void;
  domain: Ref<Domain>;
  file: Ref<File | null>;
  inputOrigin: Ref<InputOrigin>;
  loadServerPreview: (assetId: string) => Promise<void>;
  loadStreamPreview: (sourceId: string) => Promise<void>;
  mediaUrl: Ref<string>;
  mode: Ref<MediaMode>;
  onPreviewError: (error: unknown) => void;
  resetResult: () => void;
  serverPreviewUrl: Ref<string>;
  sourceId: Ref<string>;
  sourceName: Ref<string>;
  sourceUrl: Ref<string>;
  sources: Ref<MediaSource[]>;
}

export function useParseMediaInput(options: ParseMediaInputOptions) {
  let preloadSequence = 0;

  function extractLocalVideoFrame(selectedFile: File): void {
    const video = document.createElement("video");
    video.preload = "auto";
    video.src = URL.createObjectURL(selectedFile);
    video.muted = true;
    video.playsInline = true;
    video.currentTime = 0.001;
    video.onloadeddata = () => {
      try {
        video.currentTime = 0.001;
      } catch {
        // Seeking can be rejected until a browser buffers the local file.
      }
    };
    video.onseeked = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 360;
        const context = canvas.getContext("2d");
        if (context) {
          context.drawImage(video, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/jpeg");
          if (dataUrl && !options.serverPreviewUrl.value)
            options.serverPreviewUrl.value = dataUrl;
        }
      } catch {
        // A malformed local video must not block parsing.
      }
      URL.revokeObjectURL(video.src);
    };
    video.onerror = () => URL.revokeObjectURL(video.src);
  }

  async function autoPreloadAsset(selectedFile: File): Promise<void> {
    const sequence = ++preloadSequence;
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("kind", options.mode.value);
      form.append("domain", options.domain.value);
      const asset = await api<MediaAsset>("/api/v1/media/assets", {
        method: "POST",
        body: form,
      });
      if (sequence !== preloadSequence || options.file.value !== selectedFile)
        return;
      options.assets.value = [
        asset,
        ...options.assets.value.filter(
          (item) => item.asset_id !== asset.asset_id,
        ),
      ];
      await options.loadServerPreview(asset.asset_id);
    } catch {
      // Preview preloading is best-effort and must not block the selected file.
    }
  }

  function selectFile(event: Event): void {
    const selected = (event.target as HTMLInputElement).files?.[0] ?? null;
    options.inputOrigin.value = "upload";
    options.assetId.value = "";
    options.file.value = selected;
    options.clearMediaUrl();
    options.resetResult();
    if (!selected) return;
    options.mediaUrl.value = URL.createObjectURL(selected);
    if (options.mode.value === "video") {
      extractLocalVideoFrame(selected);
      void autoPreloadAsset(selected);
    } else if (options.mode.value === "document") {
      void autoPreloadAsset(selected);
    }
  }

  async function ensureSource(): Promise<string> {
    if (options.sourceId.value) return options.sourceId.value;
    const source = await api<MediaSource>("/api/v1/media/sources", {
      method: "POST",
      body: JSON.stringify({
        name: options.sourceName.value,
        url: options.sourceUrl.value,
      }),
    });
    options.sources.value = [source, ...options.sources.value];
    options.sourceId.value = source.source_id;
    return source.source_id;
  }

  async function previewNewStream(): Promise<void> {
    if (!options.sourceUrl.value) return;
    try {
      await options.loadStreamPreview(await ensureSource());
    } catch (caught) {
      options.onPreviewError(caught);
    }
  }

  function selectLibraryAsset(): void {
    options.file.value = null;
    options.clearMediaUrl();
    options.resetResult();
    if (options.assetId.value)
      void options.loadServerPreview(options.assetId.value);
  }

  async function uploadSelectedAsset(): Promise<MediaAsset> {
    const form = new FormData();
    form.append("file", options.file.value as File);
    form.append("kind", options.mode.value);
    form.append("domain", options.domain.value);
    const asset = await api<MediaAsset>("/api/v1/media/assets", {
      method: "POST",
      body: form,
    });
    options.assets.value = [
      asset,
      ...options.assets.value.filter(
        (item) => item.asset_id !== asset.asset_id,
      ),
    ];
    void options.loadServerPreview(asset.asset_id);
    return asset;
  }

  async function ensureAssetLoaded(assetId: string): Promise<MediaAsset> {
    const existing = options.assets.value.find(
      (item) => item.asset_id === assetId,
    );
    if (existing) return existing;
    const asset = await api<MediaAsset>(
      `/api/v1/media/assets/${encodeURIComponent(assetId)}`,
    );
    options.assets.value = [asset, ...options.assets.value];
    return asset;
  }

  async function selectAssetById(assetId: string): Promise<void> {
    const asset = await ensureAssetLoaded(assetId);
    if (asset.kind === "stream") return;
    options.mode.value = asset.kind;
    options.inputOrigin.value = "library";
    options.assetId.value = asset.asset_id;
    options.file.value = null;
    await options.loadServerPreview(asset.asset_id);
  }

  return {
    ensureSource,
    previewNewStream,
    selectAssetById,
    selectFile,
    selectLibraryAsset,
    uploadSelectedAsset,
  };
}
