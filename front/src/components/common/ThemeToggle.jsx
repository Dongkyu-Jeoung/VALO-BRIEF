import { useTheme } from '../../context/ThemeContext';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isLight = theme === 'light';

  return (
    <button
      type="button"
      className="theme-toggle-btn"
      onClick={toggleTheme}
      aria-pressed={isLight}
    >
      <span className="theme-toggle-label">
        {isLight ? '라이트 모드' : '다크 모드'}
      </span>
      <span className={`theme-toggle-switch${isLight ? ' is-light' : ''}`}>
        <span className="theme-toggle-knob" />
      </span>
    </button>
  );
}