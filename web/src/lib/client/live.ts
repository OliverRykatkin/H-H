/**
 * Uppdaterar ingress och nyckeltal i klienten när en nyare release finns.
 * Element: <p data-live="national"> / data-live="party:M" / "valkrets:<slug>" /
 * "kommun:<kod>" / "region:<län>" / "institute:<namn>"; nyckeltal med data-live-metric.
 * Samma mallmotor som vid bygget → samma text för samma data.
 */
import type {
  Area, Constituency, Institutes, Manifest, National, Simulation,
} from "@contracts/contracts";
import { fetchVerified, ReleaseError } from "./release";
import { areaIngress, constituencyIngress, instituteIngress, nationalIngress, partyIngress } from "../text/ingress";

async function render(kind: string, m: Manifest): Promise<string> {
  const [type, arg] = kind.split(/:(.*)/s);
  const national = await fetchVerified<National>(m, "national.json");
  switch (type) {
    case "national":
      return nationalIngress(national, await fetchVerified<Simulation>(m, "simulation.json"), m.generatedAt);
    case "party":
      return partyIngress(arg, national, await fetchVerified<Simulation>(m, "simulation.json"));
    case "valkrets":
      return constituencyIngress(await fetchVerified<Constituency>(m, `valkrets/${arg}.json`), national);
    case "kommun":
      return areaIngress(await fetchVerified<Area>(m, `kommun/${arg}.json`));
    case "region":
      return areaIngress(await fetchVerified<Area>(m, `region/${arg}.json`));
    case "institute":
      return instituteIngress(arg, await fetchVerified<Institutes>(m, "institutes.json"));
    default:
      throw new Error(`Okänd live-typ ${type}`);
  }
}

async function updateMetrics(m: Manifest) {
  const els = document.querySelectorAll<HTMLElement>("[data-live-metric]");
  if (!els.length) return;
  const national = await fetchVerified<National>(m, "national.json");
  els.forEach((el) => {
    const [kind, key] = (el.dataset.liveMetric ?? "").split(":");
    if (kind === "bloc-seats") {
      const b = national.blocs.find((x) => x.name === key);
      if (b) el.textContent = `${b.seats} mandat`;
    } else if (kind === "seats") {
      if (national.seats[key] != null) el.textContent = String(national.seats[key]);
    }
  });
}

document.addEventListener("mandatorn:newer-release", async (ev) => {
  const m = (ev as CustomEvent<Manifest>).detail;
  try {
    for (const el of document.querySelectorAll<HTMLElement>("[data-live]")) {
      el.textContent = await render(el.dataset.live ?? "", m);
    }
    await updateMetrics(m);
  } catch (e) {
    const banner = document.getElementById("release-banner");
    if (banner) {
      banner.innerHTML = "";
      const p = document.createElement("p");
      p.className = "banner error";
      p.textContent = e instanceof ReleaseError ? e.message : "Kunde inte uppdatera siffrorna — ladda om sidan.";
      banner.append(p);
    }
  }
});
