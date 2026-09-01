import DropdownSelect from '../common/DropdownSelect';
import { gameData } from '../../constants/gameData';

export default function TeamTierSelect({ value, onChange }) {
  return (
    <div className="team-tier-select-wrapper">
      <DropdownSelect
        label="팀 디비전 선택"
        options={gameData.tiers.team}
        value={value}
        onChange={onChange}
      />
    </div>
  );
}