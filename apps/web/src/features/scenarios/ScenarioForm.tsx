import type { Scenario } from "../../api/client";

interface Props {
  scenarios: Scenario[];
  selected: string;
  onSelect: (id: string) => void;
  onSeed: () => void;
  disabled?: boolean;
}

export function ScenarioForm({ scenarios, selected, onSelect, onSeed, disabled }: Props) {
  return (
    <div className="scenario-form">
      <label htmlFor="scenario">Scenario</label>
      <select id="scenario" value={selected} onChange={(event) => onSelect(event.target.value)} disabled={disabled}>
        {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.id} v{scenario.version}</option>)}
        {!scenarios.length && <option value="recursive-a2a-mcp">recursive-a2a-mcp</option>}
      </select>
      <button type="button" className="quiet-button" onClick={onSeed} disabled={disabled}>Load seeded topology</button>
    </div>
  );
}
