import { type FormEvent } from "react";

import type { Project } from "../../lib/contracts";

type Clip = Project["clips"][number];
type CaptionConfig = Clip["plan"]["caption_config"];

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
  busy,
  onSave,
  onTranslate,
  onTrack,
  onUploadAsset,
  onRemoveAsset,
}: {
  clip: Clip;
  busy: boolean;
  onSave: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onTranslate: (
    clipId: string,
    targetLanguage: string,
    mode: "translated" | "bilingual",
  ) => Promise<unknown>;
  onTrack: (clipId: string) => Promise<unknown>;
  onUploadAsset: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onRemoveAsset: (clipId: string, assetId: string) => Promise<unknown>;
}) {
  const config = clip.plan.caption_config;
  const slices =
    clip.plan.source_slices.length > 0
      ? clip.plan.source_slices
      : [clip.plan.source];
  const zoom = clip.plan.effects.find((effect) =>
    ["punch_zoom", "slow_zoom"].includes(effect.type),
  );
  const card = clip.plan.effects.find((effect) =>
    ["question_card", "quote_card", "speaker_label"].includes(effect.type),
  );
  return (
    <details className="style-editor">
      <summary>Creative studio · captions, tracking, effects & media</summary>
      <form
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          void onSave(clip.id, event.currentTarget);
        }}
      >
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
          Enhancement level
          <select
            name="enhancement_level"
            defaultValue={clip.plan.enhancement_level}
          >
            <option value="clean">Clean</option>
            <option value="dynamic">Dynamic</option>
            <option value="aggressive">Aggressive</option>
          </select>
        </label>
        <label className="wide">
          Source slices (auto-curated or manual)
          <input
            name="source_slices"
            defaultValue={slices
              .map(
                (slice) =>
                  `${slice.start_seconds.toFixed(1)}-${slice.end_seconds.toFixed(1)}`,
              )
              .join(", ")}
            placeholder="6.7-12.8, 38.1-43.3"
            required
          />
          <small>
            Comma-separated start-end ranges. Gaps, filler and dead air are
            removed.
          </small>
        </label>

        <label className="caption-toggle wide">
          <input
            name="hook_render"
            type="checkbox"
            value="true"
            defaultChecked={clip.plan.hook?.render ?? false}
          />
          <span>
            Render hook title
            <small>Show an opening headline during the first seconds.</small>
          </span>
        </label>
        <label className="wide">
          Hook title
          <input
            name="hook_text"
            defaultValue={clip.plan.hook?.text ?? ""}
            maxLength={160}
          />
        </label>
        <label className="caption-toggle wide">
          <input
            name="cta_render"
            type="checkbox"
            value="true"
            defaultChecked={clip.plan.cta?.render ?? false}
          />
          <span>
            Render call to action
            <small>Place a concise action prompt at the payoff.</small>
          </span>
        </label>
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
        <label>
          CTA text
          <input
            name="cta_text"
            defaultValue={clip.plan.cta?.text ?? "Follow for more"}
            maxLength={160}
          />
        </label>

        <label className="caption-toggle wide">
          <input
            name="captions_enabled"
            type="checkbox"
            value="true"
            defaultChecked={config.enabled}
          />
          <span>
            Burn subtitles into this clip
            <small>Caption files remain available when disabled.</small>
          </span>
        </label>
        <label>
          Caption preset
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
        <label>
          Text color
          <input
            name="text_color"
            type="color"
            defaultValue={config.text_color}
          />
        </label>
        <label>
          Highlight color
          <input
            name="highlight_color"
            type="color"
            defaultValue={config.highlight_color}
          />
        </label>
        <label>
          Outline color
          <input
            name="outline_color"
            type="color"
            defaultValue={config.outline_color}
          />
        </label>
        <label className="wide">
          Always-highlighted words
          <input
            name="highlighted_words"
            defaultValue={config.highlighted_words.join(", ")}
            placeholder="important, offer, key phrase"
          />
        </label>
        <label className="wide">
          Corrected caption text
          <textarea
            name="caption_text_override"
            defaultValue={config.text_override ?? ""}
            placeholder="Leave blank to use the transcription verbatim."
            rows={4}
            maxLength={20000}
          />
        </label>

        <label>
          Framing
          <select name="frame_style" defaultValue={clip.plan.frame_style}>
            <option value="blurred_background">
              Full frame + soft background
            </option>
            <option value="center_crop">Fill screen (smart crop)</option>
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
        <label className="caption-toggle wide">
          <input
            name="tracking_enabled"
            type="checkbox"
            value="true"
            defaultChecked={clip.plan.tracking.enabled}
          />
          <span>
            Use smart tracking
            <small>
              {clip.plan.tracking.keyframes.length} analyzed crop points.
            </small>
          </span>
        </label>
        <label>
          Horizontal crop focus
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
          Vertical crop focus
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
          Zoom effect
          <select name="zoom_effect" defaultValue={zoom?.type ?? "none"}>
            <option value="none">None</option>
            <option value="punch_zoom">Punch zoom</option>
            <option value="slow_zoom">Slow zoom</option>
          </select>
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
        <label className="caption-toggle wide">
          <input
            name="progress_bar"
            type="checkbox"
            value="true"
            defaultChecked={clip.plan.effects.some(
              (effect) => effect.type === "progress_bar",
            )}
          />
          <span>
            Retention progress bar
            <small>Show a slim animated bar along the bottom.</small>
          </span>
        </label>
        <label>
          Overlay card
          <select name="card_type" defaultValue={card?.type ?? "question_card"}>
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
            placeholder="Optional question, quote or speaker"
            maxLength={160}
          />
        </label>
        <label>
          Overlay starts at
          <input
            name="card_time_seconds"
            type="number"
            min={0}
            step={0.1}
            defaultValue={card?.time_seconds ?? 0}
          />
        </label>
        <label>
          Overlay duration
          <input
            name="card_duration_seconds"
            type="number"
            min={0.5}
            max={8}
            step={0.1}
            defaultValue={Number(card?.parameters.duration_seconds ?? 2.5)}
          />
        </label>
        <button disabled={busy}>
          {busy ? "Rendering preview…" : "Apply & preview"}
        </button>
      </form>

      <div className="enhancement-tools">
        <form
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            void onTranslate(
              clip.id,
              String(data.get("target_language")),
              data.get("translation_mode") as "translated" | "bilingual",
            );
          }}
        >
          <strong>Caption translation</strong>
          <label>
            Target language
            <input
              name="target_language"
              defaultValue={config.target_language ?? "en"}
              pattern="[A-Za-z]{2,3}"
              required
            />
          </label>
          <label>
            Display
            <select
              name="translation_mode"
              defaultValue={
                config.translation_mode === "bilingual"
                  ? "bilingual"
                  : "translated"
              }
            >
              <option value="translated">Translation only</option>
              <option value="bilingual">Bilingual</option>
            </select>
          </label>
          <button className="secondary" disabled={busy}>
            Translate & preview
          </button>
        </form>
        <button
          className="secondary"
          type="button"
          disabled={busy}
          onClick={() => void onTrack(clip.id)}
        >
          Analyze face/action tracking
        </button>
      </div>

      <form
        className="secondary-media-form"
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          void onUploadAsset(clip.id, event.currentTarget);
        }}
      >
        <strong>Add gameplay, B-roll, reaction, SFX or music</strong>
        <label className="caption-toggle wide">
          <input
            name="authorization_confirmed"
            type="checkbox"
            value="true"
            required
          />
          <span>
            I own or license this media
            <small>
              Required before attaching any gameplay, B-roll, sound or music.
            </small>
          </span>
        </label>
        <label>
          Package
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
        <label className="wide">
          Media file
          <input name="media" type="file" accept="video/*,audio/*" required />
        </label>
        <label>
          Start on clip (optional)
          <input
            name="start_seconds"
            type="number"
            min={0}
            step={0.1}
            placeholder="0"
          />
        </label>
        <label>
          End on clip (optional)
          <input
            name="end_seconds"
            type="number"
            min={0}
            step={0.1}
            placeholder="Full clip"
          />
        </label>
        <button className="secondary" disabled={busy}>
          Attach & preview
        </button>
      </form>
      {clip.plan.secondary_media.length > 0 && (
        <ul className="secondary-media-list">
          {clip.plan.secondary_media.map((asset) => (
            <li key={asset.asset_id}>
              <span>
                {asset.kind.replace("_", " ")} · {asset.filename}
              </span>
              <button
                type="button"
                className="danger-button"
                disabled={busy}
                onClick={() => void onRemoveAsset(clip.id, asset.asset_id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <small>
        Uploaded media must be yours or licensed for reuse. Final output stays
        local.
      </small>
    </details>
  );
}
