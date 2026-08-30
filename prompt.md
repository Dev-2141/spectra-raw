You are building a complete non-hardware software product called:

SPECTRA-SCAN AI
Adaptive Smart Scan Scheduler for Simulated Electronic Support Spectrum Surveillance

This is a receive-only, simulation-only, educational/research prototype. Do not implement jamming, spoofing, offensive transmission, emitter targeting, real military emitter libraries, real classified RF data, or operational EW tactics. Use only synthetic RF environments and public-style simulated spectrum data.

The product goal:
Build a polished web application that demonstrates how an Electronic Support receiver with limited instantaneous bandwidth can intelligently scan a wide spectrum. The receiver cannot observe all bands at once, so the AI scheduler must decide which band to scan next, how long to dwell, and how to improve based on hits, misses, false alarms, and reward.

Final product must include:
- Synthetic RF environment simulator
- Receiver digital twin
- Smart scan schedulers
- DeepSense-style synthetic dataset generator
- HackRF Sweep Visualizer / SignalDeck-style dashboard
- Strategy comparison engine
- Metrics dashboard
- Explainable AI decision log
- Exportable run reports
- Clean README and setup instructions

Preferred stack:
Frontend: React + Vite + TypeScript
UI: Tailwind CSS or clean CSS modules
Charts: ECharts, Plotly.js, or Recharts
Backend: Python FastAPI
Simulation/ML: NumPy, Pandas, Scikit-learn, optional PyTorch
Storage: local JSON/CSV files first, SQLite optional
Testing: pytest for backend, basic frontend sanity checks

Product style:
A dense technical dashboard, not a landing page. Dark RF-analysis interface. Show spectrum, waterfall, heatmap, active emitters, receiver scan path, decisions, metrics, and comparison charts. Avoid decorative marketing sections.

Core simulation model:
- The full spectrum is divided into frequency bands.
- Time advances in discrete time slots.
- Each band can contain transmission or no transmission.
- Emitters may be constant, bursty, periodic, frequency-hopping, low-duty-cycle, or high-priority intermittent.
- The receiver observes only one band or a limited scan window at a time.
- A scan is a hit if the receiver scans an active band and detects it.
- A false alarm occurs if the receiver reports signal where none exists.
- A missed opportunity occurs if another active band transmits while receiver is elsewhere.
- The scheduler learns from observations.

Metrics:
- Probability of detection
- False alarm rate
- Interception ratio
- Average intercept delay
- Average reward
- High-priority detection rate
- Missed opportunity count
- Scan coverage
- Average revisit time
- Correct prediction percentage

Reward examples:
+10 high-priority detection
+5 normal detection
+1 correct inactive prediction
-2 empty scan
-4 false alarm
-6 missed active signal
-10 missed high-priority signal
-1 retune/dwell cost

Build in exactly 5 steps. At the end of each step, run what can be verified, summarize changed files, list remaining issues, and STOP. Ask the user to type “continue step N”.

STEP 1: Product Scaffold and Simulation Core
Create the full project structure:
- /backend
- /backend/app
- /backend/app/models
- /backend/app/simulation
- /backend/app/schedulers
- /backend/app/api
- /backend/app/metrics
- /backend/data
- /frontend
- /docs

Backend setup:
- FastAPI app
- CORS enabled for frontend
- /api/health endpoint
- /api/state endpoint
- /api/simulation/reset endpoint
- /api/simulation/step endpoint
- /api/simulation/run endpoint

Implement core data models:
- Band
- Emitter
- RFEnvironmentConfig
- RFEnvironmentState
- ReceiverConfig
- ReceiverState
- ScanDecision
- DetectionEvent
- SimulationStepResult
- SchedulerMetrics

Implement synthetic RF environment:
- Configurable number of bands, default 64
- Configurable time slots, default 1000
- Configurable emitter density
- Configurable noise floor
- Configurable SNR range
- Ground truth activity matrix
- Power matrix
- Threat matrix
- Emitter metadata

Emitter behaviors:
- constant: active for long duration
- burst: short random bursts
- periodic: active every fixed interval
- hopping: moves across bands over time
- low_duty: rare short emissions
- priority: intermittent but high-value

Implement receiver digital twin:
- current band
- dwell time
- retune delay
- detection threshold
- detection probability based on SNR
- false alarm probability
- history of visited bands
- history of detections

Implement baseline schedulers:
- RoundRobinScheduler
- RandomScheduler

Step 1 frontend:
Create minimal React dashboard shell:
- top header with product name
- left control panel placeholder
- main heatmap placeholder
- right metrics placeholder
- status bar

Definition of done for Step 1:
- Backend starts successfully
- Frontend starts successfully
- Simulation reset creates environment
- Simulation step advances one time slot
- Round-robin and random scan decisions work
- API returns JSON state
- Stop after verification

STEP 2: Smart Schedulers and Learning Logic
Implement advanced schedulers:
1. PriorityScoreScheduler
Scores bands using:
- recent activity
- time since last visit
- uncertainty
- threat score
- periodicity estimate
- previous hit rate

2. EpsilonGreedyBanditScheduler
- Treat each band as an arm
- Maintain estimated value per band
- Explore with epsilon
- Exploit highest-value band
- Update values using rewards

3. UCB1BanditScheduler
- Encourage exploration of under-scanned bands
- Use confidence bonus
- Avoid division-by-zero issues

4. ThompsonSamplingScheduler, optional if time permits
- Beta distribution for hit probability
- Sample probability per band

5. QLearningScheduler
State features:
- current band bucket
- recent hit bucket
- time since last visit bucket
- threat bucket
- time modulo periodic window
Action:
- choose next band
Q-table:
- dictionary or NumPy table
Training:
- update Q values after each step
- alpha, gamma, epsilon configurable

Create scheduler registry:
- round_robin
- random
- priority
- epsilon_bandit
- ucb_bandit
- q_learning

Implement reward engine:
- Takes ground truth, decision, detection event, receiver state
- Produces numeric reward and explanation components

Implement learning feedback:
After each scan, update:
- visit counts
- hit counts
- miss counts
- false alarm counts
- reward history
- band priority values
- predicted activity probabilities

Add explainability:
Each scheduler decision must return:
- selected band
- confidence score
- top 3 reasons
- alternative candidate bands
- short human-readable explanation

Definition of done for Step 2:
- User can select scheduler through API
- Every scheduler can run 500+ steps without crashing
- Reward history updates
- Smart schedulers show decision explanations
- Q-learning can train over multiple episodes
- Stop after verification

STEP 3: DeepSense-Style Dataset and Strategy Comparison
Implement synthetic dataset generator:
- Generate time-frequency heatmap arrays
- Generate occupancy labels
- Generate signal power/SNR arrays
- Generate emitter type labels
- Save dataset as JSON metadata + NPY/CSV matrices
- Load saved datasets
- Replay saved dataset as simulation environment

Dataset fields:
- dataset_id
- created_at
- number_of_bands
- number_of_time_slots
- emitters
- occupancy_matrix
- power_matrix
- threat_matrix
- snr_matrix
- labels

Dataset manager API:
- POST /api/dataset/generate
- GET /api/dataset/list
- GET /api/dataset/{id}
- POST /api/dataset/{id}/load
- GET /api/dataset/{id}/stats

Dataset stats:
- occupancy percentage
- active band count
- active time count
- emitter type distribution
- average SNR
- threat distribution
- sparsity score

Strategy comparison engine:
Run multiple schedulers against same environment seed:
- round_robin
- random
- priority
- epsilon_bandit
- ucb_bandit
- q_learning

Comparison output:
- final metrics table
- reward over time
- detection rate over time
- average intercept delay
- high-threat detection rate
- scan coverage
- missed opportunity count

Add report export:
- Export comparison results as JSON
- Export metrics as CSV
- Optional PDF/HTML summary if easy

Definition of done for Step 3:
- Generate dataset from UI/API
- Load dataset into simulation
- Run strategy comparison from API
- Same scenario seed used across strategies
- Comparison metrics are not hardcoded
- Stop after verification

STEP 4: Full Dashboard UI
Build a polished frontend.

Main layout:
- Left sidebar: simulation controls and scheduler selection
- Center: live spectrum chart and waterfall heatmap
- Right panel: metrics, selected band, active decision explanation
- Bottom panel: event log and reward timeline

Views/tabs:
1. Live Monitor
2. Strategy Comparison
3. Dataset Lab
4. Training Runs
5. Explainability Log
6. Reports

Live Monitor:
- Spectrum line chart: frequency band vs power
- Highlight currently scanned band
- Mark detected active bands
- Show threshold line
- Show time slot counter
- Show selected scheduler

Waterfall/heatmap:
- x-axis bands
- y-axis recent time slots
- color signal strength
- overlay receiver scan path
- separate markers for hit, miss, false alarm

Control panel:
- Start / pause / reset
- Step once
- Run N steps
- Simulation speed slider
- Scheduler dropdown
- Number of bands
- Emitter density
- Noise level
- Detection threshold
- Dwell time
- Retune delay
- Random seed input

Metrics cards:
- detection probability
- false alarm rate
- average intercept delay
- average reward
- coverage
- high-priority detection rate
- missed opportunities
- current selected band

Strategy Comparison view:
- Button: run comparison
- Metrics table
- Bar charts
- Reward line chart
- Detection rate chart
- Winner badge based on weighted score

Dataset Lab:
- Generate dataset form
- Dataset list
- Dataset stats
- Load dataset button
- Preview heatmap

Explainability Log:
Each row:
- time
- scheduler
- selected band
- confidence
- reward
- explanation
- top factors

Design requirements:
- Must look like serious RF analytics software
- Use compact panels, technical colors, readable typography
- No giant hero page
- No filler explanations inside app
- UI must be usable on laptop screen
- Make charts responsive

Definition of done for Step 4:
- User can run simulation entirely from frontend
- Heatmap updates live
- Metrics update live
- Scheduler explanations appear live
- Strategy comparison view works
- Dataset lab works
- Stop after verification

STEP 5: Polish, Validation, Documentation, Demo Readiness
Add product polish:
- Loading states
- Error states
- Empty states
- Clean defaults
- Example scenario presets:
  - Sparse Environment
  - Dense Emitter Environment
  - Frequency Hopping Challenge
  - Periodic Radar-Like Challenge
  - High-Threat Low-Duty Challenge
  - Noisy Spectrum Challenge

Add scenario preset descriptions in code/config, not as a marketing page.

Improve metrics correctness:
- Detection probability = detections / active opportunities scanned or suitable defined denominator
- False alarm rate = false alarms / inactive scans
- Interception ratio = detected emitter events / total emitter events
- Average intercept delay = average time between emitter active start and first detection
- Coverage = unique scanned bands / total bands
- Revisit time = average time between visits to same band

Add tests:
Backend pytest tests for:
- environment generation shape
- emitter activity exists
- receiver step advances time
- round robin cycles correctly
- reward engine returns expected signs
- strategy comparison returns all strategies
- dataset save/load roundtrip

Add documentation:
README must include:
- project overview
- problem statement mapping
- why open-loop scanning is weak
- how the simulator works
- how schedulers work
- reward function explanation
- metrics explanation
- how to run backend
- how to run frontend
- how to run tests
- demo script for judges
- limitations
- safety note: simulation-only, receive-only concept, no transmission/jamming

Create demo script:
1. Open dashboard
2. Start round-robin baseline
3. Show missed opportunities
4. Switch to priority scheduler
5. Show improved detection
6. Run strategy comparison
7. Show heatmap and scan path
8. Open explainability log
9. Generate dataset
10. Export report

Final definition of done:
- Fresh install instructions work
- Backend and frontend start
- Simulation runs without hardware
- Smart schedulers outperform baseline in at least one preset
- Dashboard looks polished
- README is judge-ready
- No offensive RF capability exists
- Final response includes exact run commands
