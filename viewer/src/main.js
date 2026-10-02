import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { createIcons, Maximize, Rotate3d, Download } from "lucide";
import "./style.css";

createIcons({ icons: { Maximize, Rotate3d, Download } });
const $ = (id) => document.getElementById(id);
const viewport = $("viewport");
const world = new THREE.Scene();
world.background = new THREE.Color("#edf2ef");
const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 10000);
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  preserveDrawingBuffer: true,
});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
viewport.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotateSpeed = 0.7;
const group = new THREE.Group();
world.add(group);
const material = new THREE.PointsMaterial({
  size: 2,
  vertexColors: true,
  sizeAttenuation: false,
});
const cloud = new THREE.Points(new THREE.BufferGeometry(), material);
group.add(cloud);
const pathMaterial = new THREE.LineBasicMaterial({
  color: "#d85059",
  depthTest: false,
});
const trajectory = new THREE.Line(new THREE.BufferGeometry(), pathMaterial);
trajectory.renderOrder = 2;
group.add(trajectory);
const cursor = new THREE.Mesh(
  new THREE.SphereGeometry(0.035, 12, 8),
  new THREE.MeshBasicMaterial({ color: "#c63e4c", depthTest: false }),
);
cursor.renderOrder = 3;
group.add(cursor);
let sceneData,
  manifest,
  single = false,
  loadToken = 0;
const colors = ["#8b97a0", "#c69338", "#327f73"].map(
  (color) => new THREE.Color(color),
);

function resize() {
  const { width, height } = viewport.getBoundingClientRect();
  renderer.setSize(width, height);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(viewport);

function fit() {
  if (!sceneData) return;
  const box = new THREE.Box3().setFromBufferAttribute(
    cloud.geometry.getAttribute("position"),
  );
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const distance =
    Math.max(size.length(), 0.5) /
    Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
  camera.position
    .copy(center)
    .add(
      new THREE.Vector3(0.75, 0.5, 0.85)
        .normalize()
        .multiplyScalar(distance * 0.7),
    );
  controls.target.copy(center);
  camera.near = Math.max(distance / 10000, 0.00001);
  camera.far = distance * 100;
  camera.updateProjectionMatrix();
  controls.update();
}

function updatePoints() {
  if (!sceneData) return;
  const threshold = Number($("confidence").value);
  const selected = Number($("frame").value);
  const positions = [],
    vertexColors = [];
  for (let i = 0; i < sceneData.confidence.length; i++) {
    const confidence = sceneData.confidence[i];
    if (
      confidence < threshold ||
      (single && sceneData.frame_indices[i] !== selected)
    )
      continue;
    positions.push(
      sceneData.points[i * 3],
      sceneData.points[i * 3 + 1],
      sceneData.points[i * 3 + 2],
    );
    vertexColors.push(
      colors[confidence].r,
      colors[confidence].g,
      colors[confidence].b,
    );
  }
  cloud.geometry.dispose();
  cloud.geometry = new THREE.BufferGeometry();
  cloud.geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  );
  cloud.geometry.setAttribute(
    "color",
    new THREE.Float32BufferAttribute(vertexColors, 3),
  );
  cloud.geometry.computeBoundingSphere();
  $("frame-label").textContent = sceneData.frames[selected].id;
  $("frame-count").textContent = `${selected + 1} / ${sceneData.frames.length}`;
  $("stats").textContent =
    `${(positions.length / 3).toLocaleString()}${sceneData.full_point_count ? ` / ${sceneData.full_point_count.toLocaleString()}` : ""} points | scale unverified`;
  cursor.position.fromArray(sceneData.trajectory[selected]);
  $("status").textContent = positions.length
    ? ""
    : "No points match the current filters";
  window.planforgeDiagnostics = {
    pointCount: positions.length / 3,
    capture: sceneData.capture_id,
    frame: selected,
    single,
    scaleStatus: sceneData.scale_status,
  };
}

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(`Could not load ${url} (${response.status})`);
  return response.json();
}

async function loadCapture() {
  const token = ++loadToken;
  $("status").classList.remove("error");
  $("status").textContent = "Loading point cloud...";
  try {
    const entry = manifest.captures[Number($("capture").value)];
    const raw = $("layer").value === "raw" && entry.raw_scene;
    const data = await fetchJSON(raw ? entry.raw_scene : entry.scene);
    if (token !== loadToken) return;
    sceneData = data;
    $("frame").max = sceneData.frames.length - 1;
    $("frame").value = 0;
    trajectory.geometry.dispose();
    trajectory.geometry = new THREE.BufferGeometry().setFromPoints(
      sceneData.trajectory.map((p) => new THREE.Vector3(...p)),
    );
    $("download").href =
      `${sceneData.capture_id}/${raw ? "raw.ply" : "cloud.ply"}`;
    $("hypothesis").replaceChildren();
    for (const [label, value] of Object.entries({
      "Depth scale": sceneData.hypothesis.depth_scale,
      Intrinsics: sceneData.hypothesis.intrinsics,
      "Camera axes": sceneData.hypothesis.camera_axes,
      "Pose direction": sceneData.hypothesis.pose_direction,
      "Scale status": "Unverified",
      ...(sceneData.diagnostics
        ? {
            "Voxel size": `${sceneData.config.voxel_size} pose units`,
            "Input frames":
              sceneData.diagnostics.selected_frames.toLocaleString(),
            "Raw samples": sceneData.diagnostics.raw_points.toLocaleString(),
            "Filtered voxels":
              sceneData.diagnostics.filtered_points.toLocaleString(),
            "Outliers removed":
              sceneData.diagnostics.outliers_removed.toLocaleString(),
          }
        : {}),
    })) {
      const dt = document.createElement("dt"),
        dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = value;
      $("hypothesis").append(dt, dd);
    }
    updatePoints();
    fit();
  } catch (error) {
    if (token === loadToken) {
      $("status").textContent = error.message;
      $("status").classList.add("error");
    }
  }
}

$("fit").addEventListener("click", fit);
$("rotate").addEventListener("click", () => {
  controls.autoRotate = !controls.autoRotate;
  $("rotate").setAttribute("aria-pressed", String(controls.autoRotate));
});
$("capture").addEventListener("change", loadCapture);
$("layer").addEventListener("change", loadCapture);
$("confidence").addEventListener("change", updatePoints);
$("frame").addEventListener("input", updatePoints);
$("all").addEventListener("click", () => {
  single = false;
  $("all").setAttribute("aria-pressed", "true");
  $("single").setAttribute("aria-pressed", "false");
  updatePoints();
});
$("single").addEventListener("click", () => {
  single = true;
  $("all").setAttribute("aria-pressed", "false");
  $("single").setAttribute("aria-pressed", "true");
  updatePoints();
});
$("point-size").addEventListener("input", () => {
  material.size = Number($("point-size").value);
});
$("trajectory").addEventListener("change", () => {
  trajectory.visible = cursor.visible = $("trajectory").checked;
});
renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(world, camera);
});

try {
  manifest = await fetchJSON("manifest.json");
  if (manifest.stage === "reconstruction") {
    document.title = "PlanForge AI | Reconstruction";
    $("stage").textContent = "Reconstruction";
    $("cloud-layer").hidden = false;
    $("frame-modes").hidden = true;
    $("frame-heading").textContent = "Trajectory frame";
    $("scores-title").hidden = true;
    $("scores-table").hidden = true;
  }
  manifest.captures.forEach((entry, index) => {
    const option = new Option(entry.capture_id, index);
    $("capture").add(option);
  });
  $("capture").disabled = false;
  manifest.top_candidates.forEach((row, index) => {
    const tr = document.createElement("tr");
    tr.title = row.hypothesis.key;
    [
      index + 1,
      `${row.hypothesis.depth_scale} / ${row.hypothesis.camera_axes}`,
      row.score.toFixed(4),
    ].forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    });
    $("scores").append(tr);
  });
  await loadCapture();
} catch (error) {
  $("status").textContent = error.message;
  $("status").classList.add("error");
}
