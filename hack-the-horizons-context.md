# Hack the Horizons — Background Context (Honeywell Aerospace)

Factual background only. Sourced from public pages; items marked *(unverified)* came from secondary sources that weren't independently confirmed.

---

## 1. The event

**Hack the Horizons** — Honeywell Aerospace × Carleton University Faculty of Engineering and Design (FED).

- **Kickoff:** evening of Fri Nov 6, 2026. Challenges were not revealed before kickoff.
- **Final presentations, judging, awards:** evening of Thu Nov 12, 2026.
- **Format:** "deconstructed" hackathon over ~6 days, not a single weekend; organizers said it shouldn't require all-nighters.
- **Support:** Honeywell Aerospace mentors on a dedicated Microsoft Teams channel; access to Carleton lab space, supplies and technicians (specifics — which labs, hours, equipment — were not published).
- **Stated theme areas:** advanced communications, aerospace systems, autonomous platforms, next-generation security, wireless networks.
- **Prizes:** $10k / $5k / $2k for 1st / 2nd / 3rd, split equally among team members, not tax-exempt. Other prizes and giveaways.
- **Teams:** up to 6 members, max 1 graduate student. Team Lead must be an FED student. Carleton students only. Each member registers individually.
- **Recruiting:** QR codes for Honeywell Aerospace internship/co-op postings available at event days.
- **Not published:** judging criteria, deliverable format, IP/ownership terms, rules on pre-existing code or hardware.
- **Contacts:** facultyofengineeringanddesign@cunet.carleton.ca; accessibility — Alex Leroux (Alexandra.Leroux@carleton.ca).
- Registration page: https://carleton.ca/engineering-design/hack-the-horizons-hackathon-at-carleton-university/

Honeywell has held recruitment events at Carleton before: Nov 28, 2024 and Nov 6, 2025 (the latter promoting 16-month engineering internships).
- https://carleton.ca/career/event/honeywell-recruitment-event-2/

---

## 2. Honeywell Aerospace — company structure

- Honeywell announced in Feb 2025 it would separate Aerospace into an independent public company (HQ Phoenix, ticker HONA), targeted for the second half of 2026. 2024 sales: >$15B.
- **CEO:** Jim Currier.
- **Three business units / segments:**
  - **Electronic Solutions (ES)** — President & CEO Bob Buddecke.
  - **Engines & Power Systems (E&PS)** — Dave Marinick. Propulsion, auxiliary power units, electric power.
  - **Control Systems** — Rich DeGraff. Systems for flight, life support and safety.

### Electronic Solutions (ES) segment (from SEC filings)
- ~39% of revenue (FY2025).
- Four offerings:
  - **Avionics** — integrated flight decks (Epic, Anthem), displays, flight management systems, flight controls / fly-by-wire, radios, radar, traffic & surveillance, **satellite communications / in-flight connectivity**, navigation databases.
  - **Navigation & Sensors** — air data, inertial measurement/reference units, inertial navigation, vision navigation, precision timing; multi-sensor fusion.
  - **Electromagnetic Defensive Solutions (EDS, formerly CAES)** — sensing, protection, targeting and comms in the electromagnetic spectrum; electronic warfare; defense RF; counter-UAS.
  - **Space** — radiation-hardened inertial systems, **momentum controls (e.g. reaction wheels)**, microelectronics, payloads.
- Recent acquisitions: CAES (electronic warfare), Civitanavi (alternative navigation).

Sources:
- https://www.honeywell.com/us/en/news/press-releases/2026/01/honeywell-announces-cfo-business-unit-leaders-for-honeywell-aerospace
- https://www.sec.gov/Archives/edgar/data/2089271/000162828026013549/exhibit991-10x12b.htm
- https://www.sec.gov/Archives/edgar/data/0002089271/000162828026041399/exhibit991-10x12ba2.htm
- https://www.honeywellaerospace.com/us/en/company/leadership/bob-buddecke

---

## 3. Honeywell in Ottawa / Kanata

- **Kanata site** (Kanata North tech park). Job postings describe it as a Controlled Goods Program (CGP) environment.
- **Satcom lineage:** EMS Satcom (Kanata) supplied satcom systems; Honeywell acquired EMS Technologies (~$491M) for mobile networking, rugged computing and satcom. EMS Aviation in Ottawa had been an avionics hardware supplier to Honeywell.
- **Space lineage:** Honeywell acquired COM DEV International (Feb 2015) — satellite components (multiplexers, switches, microwave, optical), with operations in Cambridge and Ottawa. Ottawa group traces back to CAL Corporation (1974) → EMS → COM DEV → Honeywell.
- **Headcount:** ~3,600 Honeywell Aerospace staff in Canada, mostly Ontario; ~500 in the space division.
- **Ottawa Greenhouse Incubator:** developing next-gen reaction wheels and optical communication links (destined for Telesat's constellation). Honeywell has received CSA contracts for optical inter-satellite links.
- **Mitacs project (Honeywell Canada, Kanata):** lab testing of sub-components/prototypes for an optical satcom terminal for LEO.

Sources:
- https://spaceq.ca/?p=13033
- https://spaceq.ca/honeywell-aerospace-awarded-csa-contracts-for-next-gen-satellite-technologies/
- https://militaryaerospace.com/defense-executive/article/16716792/honeywell-improves-mobile-networking-rugged-computer-and-satcom-capabilities-with-ems-technologies-buy
- https://www.mitacs.ca/fr-ca/nos-projets/requirements-management-and-lab-testing-of-optical-breadboard-hardware-for-satellite-systems/
- https://www.uvic.ca/research/centres/arc/assets/docs/neil-rowlands-honeywell-ntco-agm.pdf

### Satcom product notes
- Honeywell has demonstrated in-flight switching between commercial and government satellite networks on Ka-band and L-band (JetWave MCX), positioned for contested environments.
  - https://www.honeywellaerospace.com/us/en/insights/articles/honeywell-showcases-game-changing-satcom-resiliency

---

## 4. Past Honeywell-sponsored hackathons

### ASU — "Intelligent Control" / Devils Invent: Fueling Innovation in Aerospace (Apr 10–12, 2026)
- Run by Honeywell University Relations with ASU Fulton Schools. 48 hours. 24 teams.
- Advertised problem areas: predictive maintenance, autonomous flight, smart-building efficiency; also air/thermal/integrated control systems, AI predictive models, advanced manufacturing.
- One track was "Intelligent Modelling, Optimization and Predictive Systems" (prompt: build AI/predictive models to accelerate simulation, optimize designs, detect issues early).
- **4th place ($1,000):** "Engine Sensor Blind Spot Visualizer" — XGBoost virtual sensor predicting HPC outlet temperature (T30) from other sensors on NASA CMAPSS FD001 (R² 0.984), plus remaining-useful-life model; React/Three.js 3D engine visualization + Flask backend.
  - https://github.com/BhavyaShah1234/HoneywellHackathon
- **Judges named by a participant:** Bob Buddecke (President & CEO, Electronic Solutions), Maya Chhong (Project Engineer, Honeywell Aerospace, Phoenix).
- **Mentors named:** Kristian (K.C.) Heun (Director of Strategic Planning – Academia, Honeywell Aerospace USA), Toinette Perez-Trevino (technology incubation leader — value proposition / business case).
- Organizer: Anthony Kuhn (ASU).
- https://innercircle.engineering.asu.edu/2026/03/shape-the-future-of-autonomy-the-honeywell-intelligent-control-hackathon-april-10-12/

### ASU — Devils Invent: Autonomy in Aerospace (Apr 19–21, 2024)
- Sponsored by Honeywell. Themes: autonomous vehicle control, navigation, safety; design/development/manufacturing.
- https://innercircle.engineering.asu.edu/wp-content/uploads/2024/04/Devils-Invent-Flyer-Autonomy.pdf

### ASU — Devils Invent: Aerospace Sustainability (Nov 2022)
- Sponsored by Honeywell (tied to its carbon-neutral-by-2035 pledge). Honeywell provided mentors, prizes, job opportunities. Sponsor exec: Rob Anchondo (CTO, Services & Connectivity).
- Prizes $5k / $3k / $2k / $1k. Winners were largely concept pitches with back-of-envelope numbers:
  1. Regenerative braking + supercapacitor to power taxiing (plus static-electricity harvesting).
  2. Piezoelectric taxiway plates + app tracking energy savings.
  3. Thermoelectric generation from exhaust routed through wing bleed-air system.
  4. Automated electric tugs for taxiing.
- https://news.engineering.asu.edu/2023/01/asu-students-explore-ideas-for-aerospace-sustainability/

### Others *(unverified unless linked)*
- ASU Nov 2024 "Elevating the Aerospace Workforce" — robotics, automation, training/simulation, AI workforce management; 1st place reportedly a robotics/operations-monitoring build (~$10k).
- UABC (Mexico) Honeywell–UABC Hackathon, 2nd edition, Apr 2026 — ~40 participants; phases: ideation → design → prototyping → presentation to industry experts.
- O.P.T.I.M.A (2026) — reportedly 1st of 22 teams; ML tool predicting manufacturing-tolerance problems and downstream cost.
- AeroScope (2026) — 3D engine visualization + maintenance docs + AI diagnostics + AR.
- Honeywell internal intern hackathon 2026 ("Hermes") — multi-agent knowledge graph linking industrial assets across databases.
- Honeywell Aerospace AI Hackathon, Univ. of the South Pacific, Fiji (Dec 2025) — https://fijisun.com.fj/living/technology/honeywell-explores-artificial-intelligence-talent-in-fiji
- HTS India campus hackathon (Aug 2025) — prompts included predictive maintenance in F&B manufacturing and flight-schedule optimization at congested airports — https://honeywellcampusconnect.hirepro.in
