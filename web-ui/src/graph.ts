import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { RoutingLayer, ProtocolFact } from "./routing-model";
import type { TopologyNode, TopologySnapshot } from "./types";

const roleColours: Record<TopologyNode["role"], number> = {
  host: 0x9aa6b2,
  ce: 0x4ca6a8,
  pe: 0x2e7ebc,
  core: 0xe0a340,
};
export class NetworkScene {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  private readonly renderer: THREE.WebGLRenderer;
  private readonly raycaster = new THREE.Raycaster();
  private readonly pointer = new THREE.Vector2();
  private readonly devices = new THREE.Group();
  private readonly links = new THREE.Group();
  private readonly overlay = new THREE.Group();
  private protocolLabels: {
    element: HTMLSpanElement;
    position: THREE.Vector3;
  }[] = [];
  private facts: ProtocolFact[] = [];
  private layer: RoutingLayer = "Physical";
  private readonly activity = new THREE.Group();
  private activeIds = new Set<string>();
  private reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  private readonly labels = new Map<string, HTMLButtonElement>();
  private nodeMeshes: THREE.Mesh[] = [];
  private controls: OrbitControls;
  private observer: ResizeObserver;
  private selected: string | null = null;
  private frame = 0;
  private snapshot: TopologySnapshot | null = null;
  private yaw = -0.25;
  private pitch = 0.52;
  private distance = 17;
  private drag: { x: number; y: number; moved: boolean } | null = null;
  private abort = new AbortController();

  constructor(
    private canvas: HTMLCanvasElement,
    private onSelect: (node: TopologyNode | null) => void,
  ) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
    this.renderer.setClearColor(0x0b1218, 1);
    this.scene.add(
      this.links,
      this.devices,
      this.activity,
      this.overlay,
      new THREE.HemisphereLight(0xddeeff, 0x26323d, 2.1),
    );
    const key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(3, 8, 7);
    this.scene.add(key);
    this.camera.position.set(0, 14, 18);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = false;
    this.controls.minDistance = 8;
    this.controls.maxDistance = 40;
    this.controls.maxPolarAngle = Math.PI * 0.44;
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas);
    this.bind();
    this.resize();
    this.animate();
  }
  private bind() {
    const signal = this.abort.signal;
    this.canvas.addEventListener(
      "pointerdown",
      (e) => {
        this.canvas.setPointerCapture(e.pointerId);
        this.drag = { x: e.clientX, y: e.clientY, moved: false };
      },
      { signal },
    );
    this.canvas.addEventListener(
      "pointermove",
      (e) => {
        if (!this.drag) return;
        const dx = e.clientX - this.drag.x,
          dy = e.clientY - this.drag.y;
        this.drag.moved ||= Math.hypot(dx, dy) > 4;
        this.drag.x = e.clientX;
        this.drag.y = e.clientY;
      },
      { signal },
    );
    this.canvas.addEventListener(
      "pointerup",
      (e) => {
        if (this.drag && !this.drag.moved) this.pick(e);
        this.drag = null;
      },
      { signal },
    );
    this.canvas.addEventListener("contextmenu", (e) => e.preventDefault(), {
      signal,
    });
    this.canvas.addEventListener(
      "pointercancel",
      () => {
        this.drag = null;
      },
      { signal },
    );
    window.addEventListener("resize", () => this.resize(), { signal });
  }
  setSnapshot(snapshot: TopologySnapshot) {
    if (this.snapshot?.revision === snapshot.revision) return;
    this.snapshot = snapshot;
    this.clear();
    const byId = new Map(snapshot.nodes.map((n) => [n.id, n]));
    const linkMaterial = new THREE.LineDashedMaterial({
      color: 0x526576,
      dashSize: 0.16,
      gapSize: 0.12,
      transparent: true,
      opacity: 0.9,
    });
    for (const link of snapshot.links) {
      const a = byId.get(link.source),
        b = byId.get(link.target);
      if (!a || !b) continue;
      const geometry = new THREE.BufferGeometry().setFromPoints([
        this.v(a),
        this.v(b),
      ]);
      const line = new THREE.Line(geometry, linkMaterial.clone());
      line.computeLineDistances();
      line.userData = { source: link.source, target: link.target };
      this.links.add(line);
    }
    linkMaterial.dispose();
    for (const node of snapshot.nodes) {
      const geometry =
        node.kind === "router"
          ? new THREE.CylinderGeometry(0.43, 0.43, 0.26, 16)
          : new THREE.BoxGeometry(0.7, 0.25, 0.55);
      const material = new THREE.MeshStandardMaterial({
        color: roleColours[node.role],
        roughness: 0.42,
        metalness: 0.12,
        transparent: node.state !== "up",
        opacity: node.state === "unavailable" ? 0.58 : 0.92,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(this.v(node));
      mesh.userData.nodeId = node.id;
      this.nodeMeshes.push(mesh);
      this.devices.add(mesh);
      const label = document.createElement("button");
      label.className = "graph-label";
      label.textContent = node.label;
      label.onclick = () => this.onSelect(node);
      this.canvas.parentElement?.appendChild(label);
      this.labels.set(node.id, label);
    }
    this.select(this.selected);
    this.setActivity([...this.activeIds]);
    this.setLayer(this.layer);
  }
  setProtocolFacts(facts: ProtocolFact[]) {
    if (JSON.stringify(facts) === JSON.stringify(this.facts)) return;
    this.facts = facts;
    this.setLayer(this.layer);
  }
  setLayer(layer: RoutingLayer) {
    this.protocolLabels.forEach((label) => label.element.remove());
    this.protocolLabels = [];
    this.layer = layer;
    for (const child of [...this.overlay.children]) {
      const mesh = child as THREE.Mesh;
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
      this.overlay.remove(child);
    }
    if (!this.snapshot) return;
    const byId = new Map(this.snapshot.nodes.map((n) => [n.id, n]));
    if (layer === "AS" || layer === "OSPF") {
      const groups = layer === "AS" ? [65000, 65001, 65002] : [65000];
      for (const asn of groups) {
        const nodes = this.snapshot.nodes.filter((n) => n.asn === asn);
        if (!nodes.length) continue;
        const points = nodes.map((n) => this.v(n));
        const box = new THREE.Box3().setFromPoints(points).expandByScalar(0.9);
        const size = box.getSize(new THREE.Vector3()),
          center = box.getCenter(new THREE.Vector3());
        const plane = new THREE.Mesh(
          new THREE.PlaneGeometry(size.x, size.z),
          new THREE.MeshBasicMaterial({
            color:
              asn === 65000 ? 0x447c91 : asn === 65001 ? 0x918153 : 0x77659c,
            transparent: true,
            opacity: 0.17,
            side: THREE.DoubleSide,
            depthWrite: false,
          }),
        );
        plane.rotation.x = -Math.PI / 2;
        plane.position.set(center.x, -0.3, center.z);
        this.overlay.add(plane);
      }
    }
    if (layer === "BGP" || layer === "OSPF")
      for (const p of layer === "BGP"
        ? (this.snapshot.peerings ?? [])
        : this.snapshot.links.filter((l) => l.ospf_area === "0")) {
        const a = byId.get(p.source),
          b = byId.get(p.target);
        if (!a || !b) continue;
        const start = this.v(a),
          end = this.v(b),
          mid = start.clone().lerp(end, 0.5);
        mid.y += 1.4;
        const curve = new THREE.QuadraticBezierCurve3(start, mid, end);
        const line = new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(curve.getPoints(32)),
          new THREE.LineDashedMaterial({
            color:
              this.facts.find((f) => f.id === p.id)?.state === "up"
                ? 0x62b1a0
                : this.facts.find((f) => f.id === p.id)?.state === "conflict"
                  ? 0xe0ad6a
                  : 0xaaa2cd,
            dashSize: 0.12,
            gapSize: 0.09,
          }),
        );
        line.computeLineDistances();
        this.overlay.add(line);
        const fact = this.facts.find((f) => f.id === p.id);
        if (fact) {
          const element = document.createElement("span");
          element.className = "protocol-label";
          element.textContent = fact.text;
          this.canvas.parentElement?.appendChild(element);
          this.protocolLabels.push({ element, position: curve.getPoint(0.5) });
        }
      }
  }
  setActivity(ids: string[]) {
    this.activeIds = new Set(ids);
    for (const child of this.activity.children) {
      const m = child as THREE.Mesh;
      if (this.activeIds.has(m.userData.nodeId)) delete m.userData.fadeUntil;
      else if (!m.userData.fadeUntil)
        m.userData.fadeUntil =
          performance.now() + (this.reducedMotion.matches ? 0 : 600);
    }
    for (const node of this.snapshot?.nodes ?? []) {
      const label = this.labels.get(node.id);
      if (label) {
        label.dataset.agentActive = String(this.activeIds.has(node.id));
        label.setAttribute(
          "aria-label",
          node.label + (this.activeIds.has(node.id) ? " — Agent access" : ""),
        );
      }
      if (
        !this.activeIds.has(node.id) ||
        this.activity.children.some((m) => m.userData.nodeId === node.id)
      )
        continue;
      for (const [radius, color] of [
        [0.62, 0x00e5ff],
        [0.76, 0xff36cf],
      ]) {
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(radius, radius + 0.05, 48),
          new THREE.MeshBasicMaterial({
            color,
            transparent: true,
            opacity: 0.8,
            side: THREE.DoubleSide,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        );
        ring.userData.nodeId = node.id;
        ring.position.copy(this.v(node));
        ring.position.y += 0.02;
        ring.rotation.x = -Math.PI / 2;
        this.activity.add(ring);
      }
    }
  }
  select(id: string | null) {
    this.selected = id;
    for (const mesh of this.nodeMeshes) {
      (mesh.material as THREE.MeshStandardMaterial).emissive.setHex(
        mesh.userData.nodeId === id ? 0x214d50 : 0x000000,
      );
    }
    for (const line of this.links.children) {
      const material = (line as THREE.Line)
        .material as THREE.LineDashedMaterial;
      material.color.setHex(
        line.userData.source === id || line.userData.target === id
          ? 0x5fc0bf
          : 0x526576,
      );
    }
    this.labels.forEach((el, key) => {
      el.dataset.selected = String(key === id);
    });
  }
  reset() {
    this.controls.target.set(0, 0, 0);
    this.camera.position.set(0, 14, 18);
    this.controls.update();
  }
  private v(n: TopologyNode) {
    return new THREE.Vector3(n.position.x, n.position.z, n.position.y);
  }
  private pick(e: PointerEvent) {
    const r = this.canvas.getBoundingClientRect();
    this.pointer.set(
      ((e.clientX - r.left) / r.width) * 2 - 1,
      -(((e.clientY - r.top) / r.height) * 2 - 1),
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(this.nodeMeshes)[0];
    const id = hit?.object.userData.nodeId;
    this.onSelect(this.snapshot?.nodes.find((n) => n.id === id) ?? null);
  }
  private resize() {
    const r = this.canvas.getBoundingClientRect();
    this.renderer.setSize(Math.max(1, r.width), Math.max(1, r.height), false);
    this.camera.aspect = Math.max(1, r.width) / Math.max(1, r.height);
    this.camera.updateProjectionMatrix();
  }
  private updateLabels() {
    if (!this.snapshot) return;
    const r = this.canvas.getBoundingClientRect();
    for (const label of this.protocolLabels) {
      const p = label.position.clone().project(this.camera);
      label.element.hidden = p.z < -1 || p.z > 1;
      label.element.style.left = `${((p.x + 1) * r.width) / 2}px`;
      label.element.style.top = `${((1 - p.y) * r.height) / 2}px`;
    }
    for (const n of this.snapshot.nodes) {
      const el = this.labels.get(n.id);
      if (!el) continue;
      const p = this.v(n).project(this.camera);
      el.hidden = p.z < -1 || p.z > 1;
      el.style.left = `${((p.x + 1) * r.width) / 2}px`;
      el.style.top = `${((1 - p.y) * r.height) / 2 - 28}px`;
    }
  }
  private animate = () => {
    this.frame = requestAnimationFrame(this.animate);
    this.controls.update();
    this.camera.updateMatrixWorld();
    this.updateLabels();
    for (const child of [...this.activity.children]) {
      const m = child as THREE.Mesh;
      if (m.userData.fadeUntil && performance.now() >= m.userData.fadeUntil) {
        this.activity.remove(m);
        m.geometry.dispose();
        (m.material as THREE.Material).dispose();
        continue;
      }
      const fade = m.userData.fadeUntil
        ? Math.max(0, (m.userData.fadeUntil - performance.now()) / 600)
        : 1;
      const pulse = this.reducedMotion.matches
        ? 1
        : 1 + 0.055 * Math.sin(performance.now() / 180);
      m.scale.setScalar(pulse);
      (m.material as THREE.MeshBasicMaterial).opacity =
        fade *
        (this.reducedMotion.matches
          ? 0.8
          : 0.72 + 0.15 * Math.sin(performance.now() / 180));
    }
    this.renderer.render(this.scene, this.camera);
  };
  private clear() {
    for (const group of [
      this.devices,
      this.links,
      this.activity,
      this.overlay,
    ]) {
      group.traverse((o) => {
        const x = o as THREE.Mesh;
        x.geometry?.dispose();
        const m = x.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(m) ? m : [m]).forEach((v) => v?.dispose());
      });
      group.clear();
    }
    this.protocolLabels.forEach((l) => l.element.remove());
    this.protocolLabels = [];
    this.labels.forEach((v) => v.remove());
    this.labels.clear();
    this.nodeMeshes = [];
  }
  dispose() {
    cancelAnimationFrame(this.frame);
    this.abort.abort();
    this.observer.disconnect();
    this.controls.dispose();
    this.clear();
    this.renderer.dispose();
  }
}
