import {
  Component,
  ReactNode,
  Suspense,
  useEffect,
  useLayoutEffect,
  useMemo,
} from "react";
import { Canvas, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { MovementItem, pct } from "@stock-scanner/client";
import { colors } from "@stock-scanner/design";

class SceneBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <p className="empty">
        3D is unavailable on this device. Use the movement list below.
      </p>
    ) : (
      this.props.children
    );
  }
}
function Frame({ bounds }: { bounds: THREE.Box3 }) {
  const { camera, size, invalidate } = useThree();
  useLayoutEffect(() => {
    const view = camera as THREE.OrthographicCamera;
    const center = bounds.getCenter(new THREE.Vector3());
    view.position.copy(center).add(new THREE.Vector3(7, 6, 10));
    view.lookAt(center);
    view.updateMatrixWorld();
    const projected = new THREE.Box3();
    for (const x of [bounds.min.x, bounds.max.x])
      for (const y of [bounds.min.y, bounds.max.y])
        for (const z of [bounds.min.z, bounds.max.z])
          projected.expandByPoint(
            new THREE.Vector3(x, y, z).applyMatrix4(view.matrixWorldInverse),
          );
    const span = projected.getSize(new THREE.Vector3());
    view.zoom =
      0.86 *
      Math.min(
        size.width / Math.max(span.x, 1),
        size.height / Math.max(span.y, 1),
      );
    view.updateProjectionMatrix();
    invalidate();
  }, [bounds, camera, size.width, size.height, invalidate]);
  return null;
}
function Label({
  item,
  x,
  z,
  y,
}: {
  item: MovementItem;
  x: number;
  z: number;
  y: number;
}) {
  const texture = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = 384;
    c.height = 128;
    const ctx = c.getContext("2d")!;
    ctx.textAlign = "center";
    ctx.font = "600 44px system-ui";
    ctx.fillStyle = colors.text;
    ctx.fillText(item.symbol, 192, 45);
    ctx.fillStyle =
      (item.change_percent ?? 0) < 0 ? colors.negative : colors.positive;
    ctx.font = "38px system-ui";
    ctx.fillText(pct(item.change_percent), 192, 91);
    return new THREE.CanvasTexture(c);
  }, [item.symbol, item.change_percent]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <sprite position={[x, y, z]} scale={[1.6, 0.55, 1]}>
      <spriteMaterial map={texture} transparent depthTest={false} />
    </sprite>
  );
}
export default function MovementScene({
  items,
  selected,
  onSelect,
}: {
  items: MovementItem[];
  selected?: string;
  onSelect: (symbol: string) => void;
}) {
  const supported = useMemo(() => {
    try {
      return !!document.createElement("canvas").getContext("webgl2");
    } catch {
      return false;
    }
  }, []);
  const shown = items.slice(0, 12);
  if (selected && !shown.some((i) => i.symbol === selected)) {
    const item = items.find((i) => i.symbol === selected);
    if (item) shown[shown.length - 1] = item;
  }
  const cols = Math.min(6, Math.max(1, shown.length));
  const max = Math.max(
    1,
    ...shown.map((i) => Math.min(Math.abs(i.change_percent ?? 0), 10)),
  );
  const geometry = shown.map((item, i) => {
    const x = ((i % cols) - (cols - 1) / 2) * 1.7;
    const z =
      (Math.floor(i / cols) - (Math.ceil(shown.length / cols) - 1) / 2) * 2.2;
    const change = item.change_percent;
    const h =
      change == null
        ? 0.08
        : Math.max(0.035, (Math.min(Math.abs(change), 10) / max) * 2.8);
    const y = (change ?? 0) >= 0 ? h / 2 : -h / 2;
    return { item, x, z, h, y, labelY: (change ?? 0) >= 0 ? h + 0.5 : 0.5 };
  });
  const bounds = new THREE.Box3();
  for (const { x, z, h, y, labelY } of geometry) {
    bounds.expandByPoint(
      new THREE.Vector3(x - 0.8, Math.min(y - h / 2, -0.05), z - 0.5),
    );
    bounds.expandByPoint(
      new THREE.Vector3(x + 0.8, Math.max(y + h / 2, labelY + 0.3), z + 0.5),
    );
  }
  return (
    <div className="scene-wrap">
      <div
        className="scene"
        role="img"
        aria-label="Stock movement in 3D; signed column height is percentage price change. Exact values and keyboard selection are in the list below."
      >
        {supported ? (
          <SceneBoundary>
            <Suspense fallback={<p className="empty">Loading 3D…</p>}>
              <Canvas
                frameloop="demand"
                dpr={[1, 1.5]}
                orthographic
                camera={{ position: [7, 6, 10], zoom: 48, near: 0.1, far: 100 }}
                gl={{ antialias: true, alpha: true }}
              >
                {geometry.length > 0 && <Frame bounds={bounds} />}
                <ambientLight intensity={1.4} />
                <directionalLight position={[4, 8, 5]} intensity={2} />
                <gridHelper args={[14, 14, colors.border, colors.border]} />
                {geometry.map(({ item, x, z, h, y, labelY }) => {
                  const change = item.change_percent;
                  const color =
                    change == null
                      ? colors.muted
                      : change < 0
                        ? colors.negative
                        : colors.positive;
                  return (
                    <group key={item.symbol}>
                      <mesh
                        position={[x, y, z]}
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelect(item.symbol);
                        }}
                      >
                        <boxGeometry args={[1, h, 1]} />
                        <meshStandardMaterial
                          color={color}
                          roughness={0.45}
                          metalness={0.15}
                        />
                      </mesh>
                      {selected === item.symbol && (
                        <mesh position={[x, y, z]}>
                          <boxGeometry args={[1.03, h + 0.03, 1.03]} />
                          <meshBasicMaterial color={colors.text} wireframe />
                        </mesh>
                      )}
                      <Label item={item} x={x} z={z} y={labelY} />
                    </group>
                  );
                })}
              </Canvas>
            </Suspense>
          </SceneBoundary>
        ) : (
          <p className="empty">
            3D is unavailable on this device. All values remain in the list
            below.
          </p>
        )}
      </div>
      <p className="scene-note">
        Height = price change · Zero plane = 0%
        {items.length > 12 ? ` · Showing 12 of ${items.length} symbols` : ""}
        {items.some((i) => Math.abs(i.change_percent ?? 0) > 10)
          ? " · Heights capped at 10%; labels show actual change"
          : ""}
      </p>
    </div>
  );
}
