export function ImportLanguage({ disabled }: { disabled: boolean }) {
  return (
    <label>
      Spoken language
      <select name="language" defaultValue="" disabled={disabled}>
        <option value="">Auto-detect</option>
        <option value="ur">Urdu (اردو)</option>
        <option value="en">English</option>
        <option value="hi">Hindi (हिन्दी)</option>
        <option value="ar">Arabic (العربية)</option>
        <option value="de">German</option>
        <option value="es">Spanish</option>
        <option value="fr">French</option>
      </select>
    </label>
  );
}
