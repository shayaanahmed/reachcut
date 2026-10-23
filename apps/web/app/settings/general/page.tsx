import { GeneralSettings } from "../../../features/settings/general-settings";

import { NarrationSettings } from "../../../features/informative/narration-settings";

export default function GeneralSettingsPage() {
  return (
    <GeneralSettings>
      <details className="settings-section-disclosure" id="narration-settings">
        <summary>
          <span aria-hidden="true">♫</span>
          <span>
            <strong>Voice & channel presets</strong>
            <small>
              Optional · save a voice, language and publishing defaults for
              generated shorts
            </small>
          </span>
        </summary>
        <p>
          Use these presets when creating narrated shorts. They do not change
          the audio of uploaded source videos. Choose a voice once, save a named
          preset, then select it when creating a short.
        </p>
        <NarrationSettings />
      </details>
    </GeneralSettings>
  );
}
