/* CoSoup loading study: generated cel art, deterministic 2D animation.
   Ticker labels are illustrative ingredients, never market prices or signals. */
const TAU = Math.PI * 2;
const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const smooth = (v: number) => {
  v = clamp(v);
  return v * v * (3 - 2 * v);
};
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const C = {
  teal: "#4ddac5",
  coral: "#f38a7c",
  ivory: "#f5eee2",
  gold: "#f1bf65",
  muted: "#a8bac5",
};
type Ingredient = {
  label?: string;
  kind: string;
  color: string;
  delay: number;
};
const ingredients: Ingredient[] = [
  { label: "NVDA", kind: "ticker", color: C.teal, delay: 0 },
  { label: "SPY", kind: "ticker", color: C.ivory, delay: 0.13 },
  { kind: "candle", color: C.teal, delay: 0.26 },
  { label: "AVT", kind: "ticker", color: C.gold, delay: 0.39 },
  { label: "%", kind: "symbol", color: C.coral, delay: 0.52 },
  { kind: "arrow", color: C.teal, delay: 0.65 },
  { label: "IWM", kind: "ticker", color: C.ivory, delay: 0.78 },
  { kind: "candle", color: C.coral, delay: 0.91 },
  { label: "ARW", kind: "ticker", color: C.gold, delay: 1.04 },
  { label: "$", kind: "symbol", color: C.teal, delay: 1.17 },
];

function rounded(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}
function symbol(
  ctx: CanvasRenderingContext2D,
  item: Ingredient,
  x: number,
  y: number,
  scale = 1,
  angle = 0,
  alpha = 1,
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.scale(scale, scale);
  ctx.globalAlpha = alpha;
  ctx.lineWidth = 2.6;
  ctx.strokeStyle = item.color;
  ctx.fillStyle = item.color;
  if (item.kind === "ticker") {
    const width = (item.label ?? "").length * 12 + 18;
    rounded(ctx, -width / 2, -16, width, 32, 8);
    ctx.fillStyle = "#152630";
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = item.color;
    ctx.font = "600 20px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(item.label ?? "", 0, 0);
  } else if (item.kind === "candle") {
    ctx.beginPath();
    ctx.moveTo(0, -26);
    ctx.lineTo(0, 26);
    ctx.stroke();
    rounded(ctx, -8, -14, 16, 29, 3);
    ctx.fill();
  } else if (item.kind === "arrow") {
    ctx.beginPath();
    ctx.moveTo(-20, 13);
    ctx.lineTo(-5, -2);
    ctx.lineTo(4, 6);
    ctx.lineTo(21, -15);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(8, -15);
    ctx.lineTo(21, -15);
    ctx.lineTo(21, -2);
    ctx.stroke();
  } else {
    ctx.font = "600 34px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(item.label ?? "", 0, 0);
  }
  ctx.restore();
}

export async function createAnimation(
  canvas: HTMLCanvasElement,
  sources: Record<string, string>,
) {
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) throw new Error("Canvas unavailable");
  const ctx: CanvasRenderingContext2D = context;
  const images: Record<string, HTMLImageElement> = {};
  await Promise.all(
    Object.entries(sources).map(
      ([key, url]) =>
        new Promise<void>((resolve, reject) => {
          const im = new Image();
          im.onload = () => {
            images[key] = im;
            resolve();
          };
          im.onerror = () => reject(new Error("Unable to load " + key));
          im.src = url;
        }),
    ),
  );
  const duration = 6;

  function pose(index: number, weight: number, t: number) {
    if (weight < 0.005) return;
    ctx.save();
    const sway = Math.sin((t * TAU) / duration) * 1.8;
    ctx.translate(525 + sway, 101 + Math.sin((t * TAU) / duration) * 2);
    ctx.scale(-1, 1);
    ctx.globalAlpha = weight;
    if (index === 2) {
      ctx.drawImage(
        images.toss,
        0,
        0,
        images.toss.width,
        images.toss.height,
        0,
        0,
        480,
        480,
      );
    } else {
      const cell = images.sheet.width / 2;
      const col = index === 1 || index === 3 ? 1 : 0;
      const row = index === 3 ? 1 : 0;
      // The lower-left cel extends beyond its nominal grid cell. Skip that
      // overlap when sampling a right-hand cel, retaining its original anchor.
      const inset = index === 3 ? cell * 0.12 : index === 1 ? cell * 0.05 : 0;
      ctx.drawImage(
        images.sheet,
        col * cell + inset,
        row * cell,
        cell - inset,
        cell,
        inset * (480 / cell),
        0,
        (cell - inset) * (480 / cell),
        480,
      );
    }
    ctx.restore();
  }
  function character(t: number) {
    // Crisp cel changes avoid overlapping bodies or duplicated hands.
    const keys = [
      [0, 0],
      [0.65, 3],
      [1.1, 0],
      [1.42, 1],
      [1.7, 2],
      [2.12, 1],
      [2.35, 2],
      [2.77, 1],
      [3.02, 2],
      [3.5, 1],
      [3.92, 0],
      [4.55, 3],
      [5.13, 0],
      [6, 0],
    ];
    let i = 0;
    while (i < keys.length - 2 && t >= keys[i + 1][0]) i++;
    pose(keys[i][1], 1, t);
  }
  function steam(t: number) {
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineWidth = 2;
    for (let i = 0; i < 3; i++) {
      const u = (t / duration + i / 3) % 1;
      const x = 520 + i * 36,
        y = 429 - u * 64;
      ctx.strokeStyle = `rgba(237,231,214,${0.16 * Math.sin(u * Math.PI)})`;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.bezierCurveTo(x - 13, y - 9, x + 12, y - 20, x, y - 32);
      ctx.stroke();
    }
    ctx.restore();
  }

  function render(
    time: number,
    { background = false, labels = false, serving = 0 } = {},
  ) {
    const t = ((time % duration) + duration) % duration;
    ctx.clearRect(0, 0, 720, 720);
    if (background) {
      ctx.fillStyle = "#0c151e";
      ctx.fillRect(0, 0, 720, 720);
      const glow = ctx.createRadialGradient(400, 390, 20, 400, 390, 420);
      glow.addColorStop(0, "rgba(40,90,95,.18)");
      glow.addColorStop(1, "rgba(12,21,30,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, 720, 720);
    }
    character(t);
    steam(t);
    // The clean bowl is kept small; its front wall masks ingredients as they fall inside.
    const bowlX = 365 - smooth(serving) * 36,
      bowlY = 344 + smooth(serving) * 8,
      bowlSize = 340 + smooth(serving) * 12;
    ctx.drawImage(images.bowl, bowlX, bowlY, bowlSize, bowlSize);
    for (let i = 0; i < ingredients.length; i++) {
      const item = ingredients[i],
        launch = 1.63 + item.delay,
        flight = 1.05;
      const q = (t - launch) / flight;
      const targetX = 535 + ((i % 3) - 1) * 26,
        targetY = 490;
      if (q >= 0 && q <= 1) {
        const x = mix(462, targetX, q),
          y =
            mix(290, targetY, q) - Math.sin(q * Math.PI) * (102 + (i % 3) * 14);
        symbol(
          ctx,
          item,
          x,
          y,
          mix(0.8, 0.65, q),
          Math.sin(q * TAU + i) * 0.22,
          1,
        );
      }
      const impact = launch + flight;
      if (t >= impact && t < impact + 0.55) {
        const p = (t - impact) / 0.55;
        ctx.save();
        ctx.strokeStyle = item.color;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = (1 - p) * 0.6;
        ctx.beginPath();
        ctx.ellipse(targetX, targetY + 2, 10 + 20 * p, 3 + 5 * p, 0, 0, TAU);
        ctx.stroke();
        ctx.restore();
      }
      // A few ingredients briefly remain visible on the surface, then settle.
      if (t >= impact && t < 5.35) {
        const age = t - impact,
          fade = 1 - smooth((t - 4.85) / 0.5);
        const shown = Math.min(age / 0.15, 1) * fade;
        const floatY = 478 + Math.sin(t * 2.5 + i) * 2;
        symbol(
          ctx,
          item,
          targetX,
          floatY,
          0.48,
          -0.06 + i * 0.017,
          shown * 0.7,
        );
      }
    }
    ctx.save();
    ctx.beginPath();
    ctx.rect(bowlX, bowlY + bowlSize * 0.574, bowlSize, bowlSize * 0.426);
    ctx.clip();
    ctx.drawImage(images.bowl, bowlX, bowlY, bowlSize, bowlSize);
    ctx.restore();
    if (labels) {
      ctx.fillStyle = C.ivory;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = "600 35px system-ui";
      ctx.fillText("CoSoup", 360, 48);
      ctx.fillStyle = C.muted;
      ctx.font = "15px system-ui";
      ctx.fillText("A clearer picture, one ingredient at a time.", 360, 81);
      ctx.fillStyle = C.ivory;
      ctx.font = "500 19px system-ui";
      ctx.fillText("Steve is cooking your research", 360, 663);
      for (let i = 0; i < 3; i++) {
        const a =
          0.25 +
          0.7 * ((Math.sin(((t * TAU) / duration) * 2 - i * 0.7) + 1) / 2);
        ctx.globalAlpha = a;
        ctx.fillStyle = C.teal;
        ctx.beginPath();
        ctx.arc(345 + i * 15, 698, 3, 0, TAU);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
  }
  return { render, duration };
}
