import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { Moon, Sun, Pause, Play } from "lucide-react";
import { themes } from "@stock-scanner/design";

type Theme = "light" | "dark";
const ThemeContext = createContext({
  theme: "light" as Theme,
  colors: themes.light,
  motion: true,
  reduced: false,
  toggleTheme: () => {},
  toggleMotion: () => {},
});
function preference(key: string) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function save(key: string, value: string) {
  // Only visual preferences belong here; authentication remains in its HttpOnly cookie.
  try {
    localStorage.setItem(key, value);
  } catch {
    /* Storage is optional. */
  }
}
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [systemDark, setSystemDark] = useState(
    () => matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [choice, setChoice] = useState<Theme | null>(() => {
    const value = preference("cosoup.theme");
    return value === "dark" || value === "light" ? value : null;
  });
  const [animate, setAnimate] = useState(
    () => preference("cosoup.motion") !== "paused",
  );
  const theme = choice ?? (systemDark ? "dark" : "light");
  useEffect(() => {
    const dark = matchMedia("(prefers-color-scheme: dark)");
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const onDark = () => setSystemDark(dark.matches);
    const onMotion = () => setReduced(motion.matches);
    dark.addEventListener("change", onDark);
    motion.addEventListener("change", onMotion);
    return () => {
      dark.removeEventListener("change", onDark);
      motion.removeEventListener("change", onMotion);
    };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.motion =
      animate && !reduced ? "on" : "off";
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute("content", themes[theme].background);
  }, [theme, animate, reduced]);
  return (
    <ThemeContext.Provider
      value={{
        theme,
        colors: themes[theme],
        motion: animate && !reduced,
        reduced,
        toggleTheme: () => {
          const next = theme === "light" ? "dark" : "light";
          save("cosoup.theme", next);
          setChoice(next);
        },
        toggleMotion: () => {
          save("cosoup.motion", animate ? "paused" : "on");
          setAnimate(!animate);
        },
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}
export const useTheme = () => useContext(ThemeContext);
export function ThemeControls() {
  const { theme, toggleTheme, motion, reduced, toggleMotion } = useTheme();
  return (
    <div className="theme-controls">
      <button
        className="icon-button"
        onClick={toggleMotion}
        disabled={reduced}
        aria-label={motion ? "Pause animations" : "Resume animations"}
        title={
          reduced
            ? "Reduced motion follows your device settings"
            : motion
              ? "A quieter kitchen"
              : "Bring the kitchen to life"
        }
      >
        {motion ? <Pause size={16} /> : <Play size={16} />}
      </button>
      <button
        className="icon-button"
        onClick={toggleTheme}
        aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        title={theme === "light" ? "Evening light" : "Morning light"}
      >
        {theme === "light" ? <Moon size={19} /> : <Sun size={19} />}
      </button>
    </div>
  );
}
