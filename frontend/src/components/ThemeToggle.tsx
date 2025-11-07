import { useTheme } from "../theme";
import { MoonIcon, SunIcon } from "./icons/ThemeIcons";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "深色模式" : "浅色模式";

  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={toggleTheme}
      aria-label={`切换到${label}`}
    >
      <span className="theme-toggle-indicator" aria-hidden="true">
        {isDark ? <MoonIcon className="theme-toggle-icon" /> : <SunIcon className="theme-toggle-icon" />}
      </span>
      <span>{label}</span>
    </button>
  );
}
