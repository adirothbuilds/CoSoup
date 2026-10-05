import { useEffect, useRef, useState } from "react";
import { Play, Sparkles } from "lucide-react";
import { createAnimation } from "./kitchen-animation";
import { useTheme } from "./Theme";

export function BowlMark({ className = "" }: { className?: string }) {
  const { motion } = useTheme();
  return (
    <img
      className={`bowl-mark ${className}`}
      alt=""
      width="48"
      height="48"
      src={motion ? "/mascots/bowl-idle.webp" : "/mascots/bowl-poster.webp"}
    />
  );
}
export function KitchenScene({
  working = false,
  reportId,
}: {
  working?: boolean;
  reportId?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const { motion } = useTheme();
  const [play, setPlay] = useState(false);
  const [served, setServed] = useState(false);
  const [failed, setFailed] = useState(false);
  const wasWorking = useRef(working);
  const startedWith = useRef(reportId);
  const awaitingServing = useRef(false);
  useEffect(() => {
    if (working) {
      if (!wasWorking.current) startedWith.current = reportId;
      awaitingServing.current = true;
      setServed(false);
    } else if (
      awaitingServing.current &&
      reportId &&
      reportId !== startedWith.current
    ) {
      // Job polling and report refresh can finish in either order.
      awaitingServing.current = false;
      setServed(true);
    }
    wasWorking.current = working;
  }, [working, reportId]);
  useEffect(() => {
    if (!canvas.current) return;
    const element = canvas.current;
    let frame = 0,
      disposed = false,
      visible = true,
      start = 0,
      last = 0;
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    observer.observe(element);
    createAnimation(element, {
      sheet: "/mascots/steve-poses.webp",
      toss: "/mascots/steve.webp",
      bowl: "/mascots/bowl.webp",
    })
      .then((animation) => {
        if (disposed) return;
        const cooking = working || play;
        animation.render(served ? 4.8 : 0, {
          serving: served && !motion ? 1 : 0,
        });
        if (!motion) return;
        const tick = (now: number) => {
          if (disposed) return;
          if (!start) start = now;
          if (visible && !document.hidden && now - last > 1000 / 24) {
            const elapsed = (now - start) / 1000;
            // Idle is a gentle breathing pose. Tossing is reserved for actual work or play.
            animation.render(cooking ? elapsed : served ? 4.8 : elapsed % 0.6, {
              serving: served ? Math.min(elapsed, 1) : 0,
            });
            element.dataset.frame = String(Math.floor(elapsed * 24));
            last = now;
            if (play && !working && elapsed >= animation.duration) {
              setPlay(false);
              return;
            }
            if (served && !cooking && elapsed >= 1) return;
          }
          frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
      })
      .catch(() => {
        if (!disposed) setFailed(true);
      });
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [motion, working, play, served]);
  return (
    <figure className={`kitchen-scene ${served ? "served" : ""}`}>
      <div className="kitchen-stage">
        <div className="kitchen-orbit" aria-hidden="true" />
        {failed ? (
          <img
            className="kitchen-fallback"
            src="/mascots/steve.webp"
            alt="Steve, CoSoup's chef"
          />
        ) : (
          <canvas
            ref={canvas}
            width="720"
            height="720"
            role="img"
            aria-label={
              served
                ? "Steve presents CoSoup's bowl"
                : "Steve tosses decorative stock symbols into CoSoup's bowl"
            }
          />
        )}
        <span className="kitchen-sticker">
          <Sparkles size={14} />
          {working
            ? "Let him cook…"
            : served
              ? "Order up!"
              : "Research, simmered."}
        </span>
      </div>
      <figcaption>
        <span>
          {working
            ? "Good things take a little simmer."
            : served
              ? "Fresh from the kitchen."
              : "Serious research. A less serious chef."}
        </span>
        {!working && !served && (
          <button
            className="kitchen-play"
            disabled={!motion}
            onClick={() => setPlay(!play)}
            aria-label={
              play
                ? "Stop Steve's cooking animation"
                : "Play Steve's cooking animation"
            }
            aria-pressed={play}
          >
            <Play size={12} /> Let him cook
          </button>
        )}
      </figcaption>
    </figure>
  );
}
