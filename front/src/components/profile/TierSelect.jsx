import DropdownSelect from '../common/DropdownSelect';
import { gameData } from '../../constants/gameData';

export default function TierSelect({ value, onChange }) {
  return (
    <div className="tier-select-wrapper">
      <DropdownSelect
        label="개인 티어 선택"
        options={gameData.tiers.personal}
        value={value}
        onChange={onChange}
      />
    </div>
  );
}