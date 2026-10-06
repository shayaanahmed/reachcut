import { type FormEvent, useEffect, useRef, useState } from "react";

import type { Project } from "../../lib/contracts";

type Clip = Project["clips"][number];
type CaptionConfig = Clip["plan"]["caption_config"];
type StudioTab = "story" | "captions" | "layout" | "motion" | "assets";

export type StudioPreviewState = {
  frameStyle: Clip["plan"]["frame_style"];
  cropFocusX: number;
  cropFocusY: number;
  contentMode: Clip["plan"]["content_mode"];
  captionEnabled: boolean;
  captionPosition: CaptionConfig["position"];
  captionText: string;
  fontSize: number;
  textColor: string;
  highlightColor: string;
  outlineColor: string;
  hookRender: boolean;
  hookText: string;
  ctaRender: boolean;
  ctaText: string;
  progressBar: boolean;
  zoomEffect: "none" | "punch_zoom" | "slow_zoom";
};

const tabs: { id: StudioTab; label: string; icon: string; help: string }[] = [
  { id: "story", label: "Story", icon: "◫", help: "Cuts, hook & CTA" },
  { id: "captions", label: "Captions", icon: "Aa", help: "Text & language" },
  { id: "layout", label: "Layout", icon: "⌗", help: "Frame & tracking" },
  { id: "motion", label: "Motion", icon: "↗", help: "Zoom & overlays" },
  { id: "assets", label: "Assets", icon: "+", help: "B-roll, game & SFX" },
];

const presetValues: Record<
  Exclude<CaptionConfig["preset"], "custom">,
  Partial<CaptionConfig>
> = {
  clean: {
    font_size: 54,
    animation: "none",
    highlight_color: "#D8FF42",
    max_words_per_line: 6,
  },
  bold_viral: {
    font_size: 72,
    animation: "pop",
    highlight_color: "#FFD400",
    outline_color: "#000000",
    max_words_per_line: 4,
  },
  karaoke: {
    font_size: 62,
    animation: "karaoke",
    highlight_color: "#42E8FF",
    max_words_per_line: 5,
  },
  podcast: {
    font_size: 56,
    animation: "pop",
    highlight_color: "#8BFFB0",
    position: "bottom",
    max_words_per_line: 6,
  },
  gaming: {
    font_size: 64,
    animation: "pop",
    highlight_color: "#FF4FD8",
    position: "middle",
    max_words_per_line: 4,
  },
  sports: {
    font_size: 68,
    animation: "pop",
    highlight_color: "#FFE14A",
    position: "top",
    max_words_per_line: 4,
  },
  minimal: {
    font_size: 46,
    animation: "none",
    highlight_color: "#FFFFFF",
    outline_color: "#222222",
    max_words_per_line: 7,
  },
  news: {
    font_size: 52,
    animation: "none",
    highlight_color: "#55B8FF",
    position: "bottom",
    max_words_per_line: 7,
  },
};

export function studioPreviewFromClip(clip: Clip): StudioPreviewState {
  const zoom = clip.plan.effects.find((effect) =>
    ["punch_zoom", "slow_zoom"].includes(effect.type),
  );
  return {
    frameStyle: clip.plan.frame_style,
    cropFocusX: clip.plan.crop_focus_x,
    cropFocusY: clip.plan.crop_focus_y,
    contentMode: clip.plan.content_mode,
    captionEnabled: clip.plan.caption_config.enabled,
    captionPosition: clip.plan.caption_config.position,
    captionText:
      clip.plan.caption_config.text_override ??
      clip.plan.hook?.text ??
      clip.plan.suggested_title ??
      "Your captions appear here",
    fontSize: clip.plan.caption_config.font_size,
    textColor: clip.plan.caption_config.text_color,
    highlightColor: clip.plan.caption_config.highlight_color,
    outlineColor: clip.plan.caption_config.outline_color,
    hookRender: clip.plan.hook?.render ?? false,
    hookText: clip.plan.hook?.text ?? "",
    ctaRender: clip.plan.cta?.render ?? false,
    ctaText: clip.plan.cta?.text ?? "Follow for more",
    progressBar: clip.plan.effects.some(
      (effect) => effect.type === "progress_bar",
    ),
    zoomEffect: (zoom?.type as StudioPreviewState["zoomEffect"]) ?? "none",
  };
}

function previewFromForm(
  form: HTMLFormElement,
  clip: Clip,
): StudioPreviewState {
  const data = new FormData(form);
  const override = String(data.get("caption_text_override") ?? "").trim();
  return {
    frameStyle: data.get("frame_style") as StudioPreviewState["frameStyle"],
    cropFocusX: Number(data.get("crop_focus_x")),
    cropFocusY: Number(data.get("crop_focus_y")),
    contentMode: data.get("content_mode") as StudioPreviewState["contentMode"],
    captionEnabled: data.get("captions_enabled") === "true",
    captionPosition: data.get(
      "position",
    ) as StudioPreviewState["captionPosition"],
    captionText:
      override ||
      clip.plan.hook?.text ||
      clip.plan.suggested_title ||
      "Your captions appear here",
    fontSize: Number(data.get("font_size")),
    textColor: String(data.get("text_color")),
    highlightColor: String(data.get("highlight_color")),
    outlineColor: String(data.get("outline_color")),
    hookRender: data.get("hook_render") === "true",
    hookText: String(data.get("hook_text") ?? ""),
    ctaRender: data.get("cta_render") === "true",
    ctaText: String(data.get("cta_text") ?? ""),
    progressBar: data.get("progress_bar") === "true",
    zoomEffect: data.get("zoom_effect") as StudioPreviewState["zoomEffect"],
  };
}

function applyPreset(
  form: HTMLFormElement | null,
  preset: CaptionConfig["preset"],
) {
  if (!form || preset === "custom") return;
  for (const [name, value] of Object.entries(presetValues[preset])) {
    const control = form.elements.namedItem(name);
    if (
      control instanceof HTMLInputElement ||
      control instanceof HTMLSelectElement
    )
      control.value = String(value);
  }
}

export function ClipStyleEditor({
  clip,
  saving,
  translating,
  tracking,
  assetBusy,
  mutationBusy,
  onSave,
  onTranslate,
  onTrack,
  onUploadAsset,
  onRemoveAsset,
  onPreviewChange,
  onDirtyChange,
}: {
  clip: Clip;
  saving: boolean;
  translating: boolean;
  tracking: boolean;
  assetBusy: boolean;
  mutationBusy: boolean;
  onSave: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onTranslate: (
    clipId: string,
    targetLanguage: string,
    mode: "translated" | "bilingual",
  ) => Promise<unknown>;
  onTrack: (clipId: string) => Promise<unknown>;
  onUploadAsset: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onRemoveAsset: (clipId: string, assetId: string) => Promise<unknown>;
  onPreviewChange: (preview: StudioPreviewState) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [activeTab, setActiveTab] = useState<StudioTab>("story");
  const [dirty, setDirty] = useState(false);
  const [targetLanguage, setTargetLanguage] = useState(
    clip.plan.caption_config.target_language ?? "en",
  );
  const [translationMode, setTranslationMode] = useState<
    "translated" | "bilingual"
  >(
    clip.plan.caption_config.translation_mode === "bilingual"
      ? "bilingual"
      : "translated",
  );
  const config = clip.plan.caption_config;
  const slices = clip.plan.source_slices.length
    ? clip.plan.source_slices
    : [clip.plan.source];
  const zoom = clip.plan.effects.find((effect) =>
    ["punch_zoom", "slow_zoom"].includes(effect.type),
  );
  const card = clip.plan.effects.find((effect) =>
    ["question_card", "quote_card", "speaker_label"].includes(effect.type),
  );

  useEffect(() => {
    const saveWithShortcut = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLocaleLowerCase() === "s" &&
        dirty &&
        !mutationBusy
      ) {
        event.preventDefault();
        formRef.current?.requestSubmit();
      }
    };
    window.addEventListener("keydown", saveWithShortcut);
    return () => window.removeEventListener("keydown", saveWithShortcut);
  }, [dirty, mutationBusy]);

  function tabStatus(tab: StudioTab) {
    if (tab === "story")
      return `${slices.length} cut${slices.length === 1 ? "" : "s"}`;
    if (tab === "captions") return config.enabled ? "On" : "Off";
    if (tab === "layout")
      return clip.plan.tracking.enabled ? "Tracked" : "Static";
    if (tab === "motion") return `${clip.plan.effects.length} effects`;
    return `${clip.plan.secondary_media.length} files`;
  }

  return (
    <section className="studio-controls" aria-label="Clip editing controls">
      <nav className="studio-tool-tabs" aria-label="Studio tools">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "active" : ""}
            aria-pressed={activeTab === tab.id}
            aria-controls={`studio-${tab.id}-panel`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="studio-tool-icon" aria-hidden="true">
              {tab.icon}
            </span>
            <span className="studio-tool-copy">
              <strong>{tab.label}</strong>
              <small>{tab.help}</small>
            </span>
            <small className="studio-tool-status">{tabStatus(tab.id)}</small>
          </button>
        ))}
      </nav>

      <form
        ref={formRef}
        className="studio-settings-form"
        hidden={activeTab === "assets"}
        onChange={(event) => {
          setDirty(true);
          onDirtyChange(true);
          onPreviewChange(previewFromForm(event.currentTarget, clip));
        }}
        onSubmit={async (event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const saved = await onSave(clip.id, event.currentTarget);
          if (saved !== undefined) {
            setDirty(false);
            onDirtyChange(false);
          }
        }}
      >
        <section
          className="studio-panel"
          id="studio-story-panel"
          hidden={activeTab !== "story"}
        >
          <PanelHeading
            title="Story & pacing"
            description="Control the clip structure, opening promise and final action."
          />
          <div className="studio-field-grid">
            <label>
              Content mode
              <select name="content_mode" defaultValue={clip.plan.content_mode}>
                <option value="auto">Auto detect</option>
                <option value="talking_head">Talking head</option>
                <option value="podcast">Podcast / interview</option>
                <option value="gameplay">Gameplay split-screen</option>
                <option value="sports">Sports action</option>
                <option value="tutorial">Tutorial / screen</option>
                <option value="reaction">Reaction</option>
                <option value="product">Product / commerce</option>
                <option value="news">News</option>
                <option value="broll">B-roll story</option>
              </select>
            </label>
            <label>
              Editing intensity
              <select
                name="enhancement_level"
                defaultValue={clip.plan.enhancement_level}
              >
                <option value="clean">Clean</option>
                <option value="dynamic">Dynamic</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </label>
            <label className="span-two">
              Source cuts
              <input
                name="source_slices"
                defaultValue={slices
                  .map(
                    (slice) =>
                      `${slice.start_seconds.toFixed(1)}-${slice.end_seconds.toFixed(1)}`,
                  )
                  .join(", ")}
                required
              />
              <small>
                Comma-separated ranges. Gaps are removed from the final
                timeline.
              </small>
            </label>
            <Toggle
              name="hook_render"
              checked={clip.plan.hook?.render ?? false}
              title="Opening hook"
              detail="Place a headline in the first seconds."
            />
            <label>
              Hook title
              <input
                name="hook_text"
                defaultValue={clip.plan.hook?.text ?? ""}
                maxLength={160}
              />
            </label>
            <Toggle
              name="cta_render"
              checked={clip.plan.cta?.render ?? false}
              title="End-screen CTA"
              detail="Show one clear action after the payoff."
            />
            <label>
              CTA style
              <select
                name="cta_style"
                defaultValue={clip.plan.cta?.style ?? "follow"}
              >
                <option value="follow">Follow</option>
                <option value="comment">Comment</option>
                <option value="part_two">Part two</option>
                <option value="profile">Visit profile</option>
                <option value="product">Product</option>
                <option value="campaign">Campaign</option>
              </select>
            </label>
            <label className="span-two">
              CTA text
              <input
                name="cta_text"
                defaultValue={clip.plan.cta?.text ?? "Follow for more"}
                maxLength={160}
              />
            </label>
          </div>
        </section>

        <section
          className="studio-panel"
          id="studio-captions-panel"
          hidden={activeTab !== "captions"}
        >
          <PanelHeading
            title="Captions"
            description="Build a readable visual identity and correct the transcript before rendering."
          />
          <div className="studio-field-grid">
            <Toggle
              name="captions_enabled"
              checked={config.enabled}
              title="Burn captions"
              detail="Caption files remain available when disabled."
            />
            <label>
              Preset
              <select
                name="caption_preset"
                defaultValue={config.preset}
                onChange={(event) =>
                  applyPreset(
                    event.currentTarget.form,
                    event.currentTarget.value as CaptionConfig["preset"],
                  )
                }
              >
                <option value="custom">Custom</option>
                <option value="clean">Clean</option>
                <option value="bold_viral">Bold viral</option>
                <option value="karaoke">Karaoke</option>
                <option value="podcast">Podcast</option>
                <option value="gaming">Gaming</option>
                <option value="sports">Sports</option>
                <option value="minimal">Minimal</option>
                <option value="news">News</option>
              </select>
            </label>
            <label>
              Position
              <select name="position" defaultValue={config.position}>
                <option value="bottom">Bottom</option>
                <option value="middle">Middle</option>
                <option value="top">Top</option>
              </select>
            </label>
            <label>
              Animation
              <select name="animation" defaultValue={config.animation}>
                <option value="pop">Active-word pop</option>
                <option value="karaoke">Karaoke sweep</option>
                <option value="none">None</option>
              </select>
            </label>
            <label>
              Font
              <input
                name="font_family"
                defaultValue={config.font_family}
                maxLength={80}
              />
            </label>
            <label>
              Size
              <input
                name="font_size"
                type="number"
                min={28}
                max={96}
                defaultValue={config.font_size}
              />
            </label>
            <label>
              Words per line
              <input
                name="max_words_per_line"
                type="number"
                min={2}
                max={8}
                defaultValue={config.max_words_per_line}
              />
            </label>
            <div className="color-fields">
              <label>
                Text
                <input
                  name="text_color"
                  type="color"
                  defaultValue={config.text_color}
                />
              </label>
              <label>
                Highlight
                <input
                  name="highlight_color"
                  type="color"
                  defaultValue={config.highlight_color}
                />
              </label>
              <label>
                Outline
                <input
                  name="outline_color"
                  type="color"
                  defaultValue={config.outline_color}
                />
              </label>
            </div>
            <label className="span-two">
              Highlighted words
              <input
                name="highlighted_words"
                defaultValue={config.highlighted_words.join(", ")}
                placeholder="important, offer, key phrase"
              />
            </label>
            <label className="span-two">
              Corrected caption text
              <textarea
                name="caption_text_override"
                defaultValue={config.text_override ?? ""}
                rows={5}
                maxLength={20000}
                placeholder="Leave blank to use the transcription."
              />
            </label>
          </div>
          <div className="studio-inline-tool">
            <div>
              <strong>Translate captions</strong>
              <small>Uses your local model and preserves clip timing.</small>
            </div>
            <input
              aria-label="Target language"
              value={targetLanguage}
              onChange={(event) => setTargetLanguage(event.target.value)}
              pattern="[A-Za-z]{2,3}"
            />
            <select
              aria-label="Translation display"
              value={translationMode}
              onChange={(event) =>
                setTranslationMode(event.target.value as typeof translationMode)
              }
            >
              <option value="translated">Translation only</option>
              <option value="bilingual">Bilingual</option>
            </select>
            <button
              type="button"
              disabled={mutationBusy || dirty}
              onClick={() =>
                void onTranslate(clip.id, targetLanguage, translationMode)
              }
            >
              {dirty
                ? "Save edits first"
                : translating
                  ? "Translating…"
                  : "Translate"}
            </button>
          </div>
        </section>

        <section
          className="studio-panel"
          id="studio-layout-panel"
          hidden={activeTab !== "layout"}
        >
          <PanelHeading
            title="Layout & tracking"
            description="Choose how the source fills 9:16 and where the viewer’s eye should stay."
          />
          <div className="studio-field-grid">
            <label>
              Framing
              <select name="frame_style" defaultValue={clip.plan.frame_style}>
                <option value="blurred_background">
                  Full frame + soft background
                </option>
                <option value="center_crop">Fill screen</option>
              </select>
            </label>
            <label>
              Tracking strategy
              <select
                name="tracking_strategy"
                defaultValue={clip.plan.tracking.strategy}
              >
                <option value="static">Static</option>
                <option value="face">Face</option>
                <option value="active_speaker">Active speaker</option>
                <option value="action">Action</option>
                <option value="object">Object / screen</option>
              </select>
            </label>
            <Toggle
              name="tracking_enabled"
              checked={clip.plan.tracking.enabled}
              title="Use smart tracking"
              detail={`${clip.plan.tracking.keyframes.length} crop points are available.`}
            />
            <button
              className="studio-secondary-action"
              type="button"
              disabled={mutationBusy || dirty}
              onClick={() => void onTrack(clip.id)}
            >
              {dirty
                ? "Save edits first"
                : tracking
                  ? "Analyzing…"
                  : "Re-analyze tracking"}
            </button>
            <label>
              Horizontal focus
              <input
                name="crop_focus_x"
                type="range"
                min={0}
                max={1}
                step={0.05}
                defaultValue={clip.plan.crop_focus_x}
              />
            </label>
            <label>
              Vertical focus
              <input
                name="crop_focus_y"
                type="range"
                min={0}
                max={1}
                step={0.05}
                defaultValue={clip.plan.crop_focus_y}
              />
            </label>
            <label>
              Source audio track
              <input
                name="audio_track_index"
                type="number"
                min={0}
                max={32}
                defaultValue={clip.plan.audio_track_index}
              />
            </label>
          </div>
        </section>

        <section
          className="studio-panel"
          id="studio-motion-panel"
          hidden={activeTab !== "motion"}
        >
          <PanelHeading
            title="Motion & overlays"
            description="Use a small number of intentional effects to support retention."
          />
          <div className="studio-field-grid">
            <label>
              Transition
              <select
                name="transition_style"
                defaultValue={clip.plan.transition_style}
              >
                <option value="cut">Clean cut</option>
                <option value="fade">Audio/video fade</option>
              </select>
            </label>
            <label>
              Transition duration
              <input
                name="transition_duration_seconds"
                type="number"
                min={0.05}
                max={1}
                step={0.05}
                defaultValue={clip.plan.transition_duration_seconds}
              />
            </label>
            <label>
              Zoom
              <select name="zoom_effect" defaultValue={zoom?.type ?? "none"}>
                <option value="none">None</option>
                <option value="punch_zoom">Punch zoom</option>
                <option value="slow_zoom">Slow zoom</option>
              </select>
            </label>
            <Toggle
              name="progress_bar"
              checked={clip.plan.effects.some(
                (effect) => effect.type === "progress_bar",
              )}
              title="Retention progress bar"
              detail="Show a slim timeline indicator."
            />
            <label>
              Overlay type
              <select
                name="card_type"
                defaultValue={card?.type ?? "question_card"}
              >
                <option value="question_card">Question card</option>
                <option value="quote_card">Quote card</option>
                <option value="speaker_label">Speaker label</option>
              </select>
            </label>
            <label>
              Overlay text
              <input
                name="card_text"
                defaultValue={String(card?.parameters.text ?? "")}
                maxLength={160}
                placeholder="Optional"
              />
            </label>
            <label>
              Starts at
              <input
                name="card_time_seconds"
                type="number"
                min={0}
                step={0.1}
                defaultValue={card?.time_seconds ?? 0}
              />
            </label>
            <label>
              Duration
              <input
                name="card_duration_seconds"
                type="number"
                min={0.5}
                max={8}
                step={0.1}
                defaultValue={Number(card?.parameters.duration_seconds ?? 2.5)}
              />
            </label>
          </div>
        </section>

        <div className="studio-savebar" hidden={activeTab === "assets"}>
          <div>
            <strong>
              {dirty ? "Preview has unsaved changes" : "Preview is up to date"}
            </strong>
            <small>
              {dirty ? "⌘/Ctrl + S to save" : "Safe to approve and export"}
            </small>
          </div>
          <div>
            {dirty && (
              <button
                type="button"
                className="studio-reset-button"
                disabled={mutationBusy}
                onClick={() => {
                  formRef.current?.reset();
                  setDirty(false);
                  onDirtyChange(false);
                  onPreviewChange(studioPreviewFromClip(clip));
                }}
              >
                Reset changes
              </button>
            )}
            <button type="submit" disabled={mutationBusy || !dirty}>
              {saving ? "Rendering preview…" : "Save & update preview"}
            </button>
          </div>
        </div>
      </form>

      <section
        className="studio-panel assets-panel"
        id="studio-assets-panel"
        hidden={activeTab !== "assets"}
      >
        <PanelHeading
          title="Secondary media"
          description="Layer licensed gameplay, B-roll, reactions, sound effects or music."
        />
        {dirty && (
          <div className="studio-unsaved-warning" role="status">
            <span>Unsaved edits are waiting in another tool.</span>
            <button type="button" onClick={() => setActiveTab("story")}>
              Return to save
            </button>
          </div>
        )}
        <form
          className="asset-upload-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            void onUploadAsset(clip.id, event.currentTarget);
          }}
        >
          <Toggle
            name="authorization_confirmed"
            checked={false}
            required
            title="I own or license this media"
            detail="Required before attaching an asset."
          />
          <label>
            Asset type
            <select name="kind" defaultValue="gameplay">
              <option value="gameplay">Gameplay footage</option>
              <option value="broll">B-roll</option>
              <option value="reaction">Reaction / PIP</option>
              <option value="sound_effect">Sound effect</option>
              <option value="music">Music</option>
            </select>
          </label>
          <label>
            Placement
            <select name="placement" defaultValue="bottom">
              <option value="bottom">Bottom split</option>
              <option value="pip">Picture in picture</option>
              <option value="fullscreen">Full screen</option>
              <option value="audio">Audio only</option>
            </select>
          </label>
          <label className="span-two">
            Media file
            <input name="media" type="file" accept="video/*,audio/*" required />
          </label>
          <label>
            Start (optional)
            <input name="start_seconds" type="number" min={0} step={0.1} />
          </label>
          <label>
            End (optional)
            <input name="end_seconds" type="number" min={0} step={0.1} />
          </label>
          <button disabled={mutationBusy || dirty}>
            {dirty
              ? "Save edits before attaching"
              : assetBusy
                ? "Attaching…"
                : "Attach & render preview"}
          </button>
        </form>
        {clip.plan.secondary_media.length ? (
          <div className="asset-library">
            {clip.plan.secondary_media.map((asset) => (
              <article key={asset.asset_id}>
                <span aria-hidden="true">
                  {asset.kind === "music" || asset.kind === "sound_effect"
                    ? "♫"
                    : "▶"}
                </span>
                <div>
                  <strong>{asset.filename}</strong>
                  <small>
                    {asset.kind.replaceAll("_", " ")} · {asset.placement}
                  </small>
                </div>
                <button
                  type="button"
                  disabled={assetBusy || dirty}
                  onClick={() => void onRemoveAsset(clip.id, asset.asset_id)}
                >
                  Remove
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="studio-empty-tool">No secondary media attached.</div>
        )}
      </section>
    </section>
  );
}

function PanelHeading({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <header className="studio-panel-heading">
      <div>
        <span className="eyebrow">CLIP STUDIO</span>
        <h2>{title}</h2>
      </div>
      <p>{description}</p>
    </header>
  );
}

function Toggle({
  name,
  checked,
  required = false,
  title,
  detail,
}: {
  name: string;
  checked: boolean;
  required?: boolean;
  title: string;
  detail: string;
}) {
  return (
    <label className="studio-toggle">
      <input
        name={name}
        type="checkbox"
        value="true"
        defaultChecked={checked}
        required={required}
      />
      <span>
        <strong>{title}</strong>
        <small>{detail}</small>
      </span>
    </label>
  );
}
