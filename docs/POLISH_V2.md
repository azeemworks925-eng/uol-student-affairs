# Polish v2 — Design spec (owner-approved, 24 Nov 2026)

Source of truth for the four Polish v2 sessions (P1 Foundation, P2 Pages, P3 Doodles + auth, P4 Logic). Freeze: **Thursday 26 Nov, 01:00**. If time runs out, unfinished items are cut cleanly — nothing half-built ships.

## Global rules (every page, every role)
- **Consistency first:** one thoughtful product, not three things glued together. Same components, spacing, radii, motion and colours on every page and role.
- **"Soul" everywhere:** no plain white soulless pages — colour, motion, hover life, doodles.
- **Same stat = same component, same definition, same numbers** on every dashboard.
- **Pastel palette** on Forest green; small fixed set of tints as tokens; no one-off colours.
- **Fixed status/category colour map** everywhere (complaints, voice, issues, meetings, accounts, representation; categories; voice types).
- **Mobile first-class:** every page checked at 360px.
- **Copy rule:** finished product, not a demo — no explanatory sentences, short headings, one helper line max, no "successfully", no "please", no exclamation marks. Footer disclaimer always stays.
- **Naming:** page titles match sidebar labels (student "My submissions" → "Complaints").
- **Hover life + very soft shadows.**
- **Bento grid, no holes:** mixed card shapes tile with zero gaps; equal height per row; 8px grid; 24px gaps everywhere.
- **Motion (reference: Pillio video):** static frame, content cascades in, count-ups, bars fill, sliding pills, ↗ fills dark, selection outline, popovers grow from click, buttons grey → solid when ready. Off under reduced motion.
- **Charts:** smooth draw-in, tooltips, no auto-refresh.
- **Font:** all Inter.
- **Redundant columns hidden** when every row has the same value (e.g. cohort on a student's own pages).
- **Rule sentences → pills with tooltips** ("Locked", "CR & GR only", "Private", "View only").
- **One view-control row per page** — never two toggles stacked.

## Motion & transitions
- View Transitions API for cross-page fades; sidebar/top bar stay still; active nav pill slides; hover ≠ active.
- Page-load cascade, count-ups, fills, chart draw-in.
- Timelines draw top → bottom; coloured dots pop; speech-bubble responses with role pill; resolution note as pastel quote with ✓.
- Steppers fill on load; current step pulses once.

## Messages / toasts
- No "Successfully signed in as …" anywhere. Toasts only for actions just done (bottom-right, top on phone, ~4s, pause on hover, ×). Sign-out → toast on sign-in page.

## Filters & reset
- Filter bar on every list page; active filters as removable pills; "↺ Reset · N" only when non-default; URL-based; stat cards respect filters except status and clicking one sets status; phone: pill scroller + Filters bottom sheet.

## Empty states (one component)
- Doodle → headline → one line → one action; never dashed boxes. Variants: No results (Reset filters) · Nothing yet (invitation + action; none for read-only roles) · All caught up (plane in tray ✓ + one-time sparkle).

## Forms (one pattern)
- Tier-2 banner + centred form card (~720px) + right helper card (tips / similar items).
- Live character counters instead of helper sentences (amber near limit, rose over); inline validation after first blur; auto-growing textareas; small choices as pills/segmented controls (Voice type; Category if ≤6).
- **Live duplicate check** (dsa/edit_distance.py, threshold 0.6) for complaints and section issues: similar items in the side card while typing the title (debounced ~400ms), permission-scoped, with "View" / "Support it instead"; tips doodle when none.
- Primary grey → solid when valid; Write → Review steps where a review step exists; no back links; Cancel as ghost; success → detail page + toast + plane take-off moment.

## Page headers (3 tiers)
- Tier 1 big hero only on each role's home; Tier 2 slim pastel banner on every module page and form; Tier 3 status-tinted hero on detail pages. Mobile: banner → title + action, doodle hidden < 480px.

## Doodle placement map
Restraint: ≤ 1 doodle per screen region; never in rows/cells/stat cards; sizes S 48–64 / M 96–120 / L 160–220px; original inline SVG in Google-illustration style; same recurring student character; diverse cast (boys, girls, one in hijab); paper plane = product motif (a concern being sent); pastel tokens only; idle motion only.
1. Auth (L): home = student launching the plane along Submit → Track → Resolved; secondary sign-in = student waving; wrong account = plane bumps a closed gate (once); sign-in didn't finish = plane loops around a cloud; registration/complete-profile = ID card with tick; session expired = plane resting by a clock.
2. Home heroes (L): Super Admin = department building + rising chart bars; Batch Advisor = catching paper planes into an inbox tray; CR/GR = two students with a megaphone/flag; Student = student with plane + ticked checklist.
3. Module banners (S): Complaints = plane into inbox → ✓; Issues = raised hands behind one shared sign; Student Voice = ?, lightbulb, heart bubbles; Meetings = two people at a table with calendar + clock; Students = mixed group; Staff = advisor with lanyard + cohort folder; CR/GR = podium with badges; Picker = hand pinning a badge on a student card; Academic Structure = blocks stacked as a tree; Terms = calendar with progress ribbon + leaves; Categories = coloured folders; Profile history = clipboard + clock; Notifications = bell + envelopes.
4. Detail hero corner (S), status-aware: plane in flight (received/waiting/requested) · magnifying glass (under review/reviewed/time suggested) · landed plane ✓ (resolved/answered/confirmed) · plane resting on ×-tag (rejected/declined/cancelled).
5. Empty states (M): calm module pose; magnifying glass for no results; plane in tray for all caught up; sleeping bell; calendar + coffee cup; advisor at desk for "No response yet".
6. Success moments (M, once ~1.2s): plane take-off into the stepper after submitting; hand/heart pop on Support.
7. Form side card: lightbulb + pencil tips doodle.
8. Dialog headers: mini doodle.
9. Error pages (L): 404 plane in a branch; 403 plane at a locked gate; 500 plane with a wrench; "Go home".
10. Loading: tiny plane gliding along a progress line.
11. Sidebar bottom (optional): idle plane above profile — skip if busy.

## Shared controls
- One dropdown component (no native select look; real select underneath); segmented toggles with sliding highlight; pastel pills (no outlined boxes; "Supported ✓"); one dialog; icon/⋮ row actions, destructive in soft rose with confirm; Forest notification badge; card-header link style "View all ↗"; cohort label "DEMO-A · S4".

## Dark mode
- Tokens + sun/moon toggle now (remembered, follows OS first); proper pass after Thursday; hide toggle for the demo if anything looks off.

## Shell (all roles)
- Sidebar: floating card, sliding active pill, Sign out (subtle red) + mini profile at bottom.
- Create button: menu only for 2+ actions. Advisor "+ Schedule meeting"; Super Admin "+ Add Batch Advisor"; Student/CR/GR "+ New" menu (New complaint, Voice submission, Request meeting, + Raise a section issue for CR/GR).
- Top bar: search, theme toggle, bell (panel: Today/Earlier, type icons, unread dots, Mark all read, View all, All caught up; bottom sheet on phone), avatar menu (no Django admin link). Breadcrumb is the only back.

## Global search (all roles) — P4
- Typeahead incl. backspace (debounced ~150–200ms), clearing clears, grouped (Students · Complaints · Voice · Issues/Meetings where visible), max ~8, highlighted matches, ↑/↓/Enter/Esc, "/" focuses, recent searches on empty focus, empty submit does nothing, bare "Search" page removed, "See all results" keeps the query, empty state, mobile sheet, permissions unchanged, student names via Trie (dsa/trie.py).

## Role switcher — P4 (build only if safe)
- One account, two roles (Super Admin who is also a Batch Advisor). First check whether a Super Admin can already hold AdvisorAssignment rows and use advisor views. If yes → sidebar-top "Super Admin | Advisor" switch (own home/nav/permissions, remembered, only for dual-role users, tests). If not → first post-demo task; demo uses two accounts.

## Auth family — P3
- Home: split screen (white left: logo, headline, subtext, Sign in with Google, help line, footer; pastel-Forest rounded right panel with doodle). Animated "How it works": paper plane flies along a dashed path Submit → Track → Resolved, nodes fill, ✓ at Resolved, ~6s loop, pauses on hover; feature cards (Complaints / Student Voice / Meetings) as rotating captions with dots. Mobile: panel → short band; stepper vertical. Follow Google sign-in button branding.
- Secondary sign-in: "Welcome back" / "Sign in with your UOL Google account." / [Sign in with Google] / "Students: use your @student.uol.edu.pk email." / ← Home.
- Wrong account: "That account can't sign in" / email chip / "Use your UOL student email (@student.uol.edu.pk)." / [Try another account] / ← Home.
- Sign-in didn't finish: "Sign-in didn't finish" / "Google didn't finish signing you in. Try again." / [Try again] / ← Home.
- Registration + complete-your-profile (with Male | Female); session expired. All share one compact card + doodle family.

## Super Admin — P2
- Home bento: hero (12) · 4 stat cards · complaints per week smooth area chart (8) | resolved vs open donut with centre % (4) · by category rounded bars, count and % separated (8) + by section short-label bars (8) | recent activity tall (4, icon avatars for anonymous students, status dots, clickable rows, View all). Heatmap, privacy legend and suppression footer removed. Fix "Demo" names.
- Lists/details/people/config pages as below.

## Batch Advisor — P2
- Home: hero with **"Next complaint"** (MinHeap, dsa/heap.py) as primary action + helper "Oldest waiting: N days" + tooltip + "All caught up" state; chips (term, cohorts). Stats: Open complaints · Issues waiting · Voice waiting · Meetings this week. Bento: hero · stats · open complaints per cohort bars (8) | upcoming meetings (4) · recent activity (8 tall) | Voice waiting (4) + Issues waiting (4). "Next complaint" also the Complaints banner action.
- Module pages identical to Super Admin's components; "Your cohorts" subtitle removed.

## CR/GR + Student — P2
- **Student/CR home:** hero "Good evening, <first name>" + "DEMO-A · S4" chip (+ CR/GR badge), actions "+ New complaint" / Student Voice / Request meeting (replaces Quick actions card); stats Open · Resolved · Voice answers · Upcoming meetings; bento: Your complaints (8, animated progress) | Upcoming meetings (4, Add to Google Calendar on confirmed) · Latest updates timeline (8) | Voice answers (4) · Your section (12: issue cards with Support / "Supported ✓", "+ Raise an issue" for CR/GR).
- **Section issues list:** banner + "+ Raise an issue" (CR/GR); stat filters; filter bar + Reset beside the view toggle; name + CR/GR badge inline (no wrap); support pill with hand icon + avatar stack; Open for support / Support closed pills; cohort column hidden.
- **Raise a section issue form:** forms pattern; live counters (0/120, 0/2000); live similar issues; Write → Review steps; no back link.
- **Student Complaints:** title "Complaints"; banner + "+ New complaint"; stat filters; filter bar + Reset; students default to cards view; cohort hidden; empty state "No complaints yet / Raise a concern and track it here."
- **Student Voice:** banner + "+ New submission"; "Private" pill; empty state = three invitation tiles (Ask a question / Share an idea / Give feedback, each in its type colour, opens the form with type preselected); items use card/list components (type chip, Waiting → Reviewed → Answered, answer preview).
- **Student Meetings:** default Month calendar; requested meetings as dashed chips; List groups Waiting for reply · Upcoming · Past; "Preferred: Thu 26 Nov, 16:36"; one view-control row; "+ Request a meeting".
- **Complaint form/detail:** forms pattern (category pills, counters, live similar complaints) and detail model (request cancellation where allowed).

## Detail pages (model: section issue detail) — P2
- Desktop bento 8 | 4, no holes. Left: **status-tinted hero** (reference + status pill + Locked pill where relevant, title, description, **stepper merged into the hero**, status-aware corner doodle); below it the **responses/history timeline** with "CR & GR only" pill where relevant and empty state ("No response yet"). Right (sticky): **action card** on top (e.g. Support: count-up supporters, avatar stack, Open/Closed pill, Support button that pops / "Supported ✓"; for advisors: Respond / Update status; for students: Request cancellation; oversight roles: "View only" pill) and a **details card** (raised by with badge, dates with exact time on hover, reference with copy button; short labels; no "(Batch Advisor)" repeats). Right column stretches to match. Phone: hero → action → timeline → details.
- Applies to complaint, collective/section issue, voice and meeting detail for every role.

## List pages — P2
- Tier-2 banner; filter bar + Reset; stat cards as filter tabs + status segmented tabs (replace Status dropdown); list/cards toggle + "3 | 4 per row" (remembered); tablet 2, phone 1. Cards (Pillio) with animated progress bars; list rows (Pillio lab-results). Meetings list: pastel date blocks, status colours.

## Meetings — P2
- Default **Month** calendar; toggle Month · Week · List (remember last); header: month + Today + ‹ › icons + status pills (+ Reset). Month grid fills the page, chips in day cells (status colour, time + name), pending dashed, Declined/Cancelled hidden by default, "+N more", today = Forest circle; day popover grows from the cell; meeting detail card with actions for whoever can act (Super Admin view only). Week: time grid, blocks sized by duration, today tinted, live "now" line, overlaps side by side (dsa/intervals.py). Grid slides on ‹ ›. Mobile: compact grid + agenda. Schedule/Request form with amber overlap note. **Google Calendar option A:** pre-filled "Add to Google Calendar" link + ".ics" on confirmed meetings (permission-checked). No Calendar API.

## People (Super Admin) — P2 (+ gender in P4)
- Students: equal-height cards, pastel avatars, stat filters, filter bar + Reset, gender filter + sort (P4), Add student dialog (Full name, email with live check, Gender in P4). Profile history as old → new timeline with empty state. Staff: Advisors | Super Admins segmented, Google linked / Not linked pills, cohort pills, fix demo names.

## CR/GR management — P2 + P4
- Filter pills + Reset (no native selects, no Apply); cohort cards with short title "DEMO-A · Semester 4", CR and GR person tiles, status pill, "Replace CR"/"Replace GR", history timeline, dashed "+ Appoint" slot.
- **Picker page (P4):** full page "Appoint CR/GR — DEMO-A · S4": current holder, Trie-powered search with instant suggestions, selectable student cards, review strip "Current → New", Confirm grey → solid, toast. Same locking/audit services.
- **Swap CR and GR removed (P4)** — GR is the Girls' Representative.

## Gender field — P4
- StudentProfile.gender (Male/Female); registration asks it; existing students complete it at next sign-in before reaching home; edits audited via StudentProfileChange. **GR must be Female (server-enforced)**; GR picker lists only girls; **CR can be anyone**. Students filter/sort by gender. Visible only to Super Admin + the cohort's Batch Advisors. Seed genders; tests; DECISIONS.md.

## Configuration — P2
- Academic Structure: three equal-height cards (no holes), compact rows with count pills + icon actions, "+ Add" → dialog; Department tree (dsa/tree.py) full width with smooth expand/collapse and count pills.
- Academic Terms: chip "Overview uses Fall 2026"; term cards with Current pill and animated term-progress bar; Add term dialog.
- Complaint Categories: "+ Add category" dialog; rows with colour dot, Active pill, count pills; ↑/↓ icons with smooth reorder animation.

## Other P4 logic
- Remove small-cohort suppression entirely (code, legend, footer, tests).
- Demo-data cleanup: replace junk test content ("Sad", "AC is dead", "0000…", "odnojwndkjw", "jsxnsjxjscns") and "Demo …" names with realistic data.
- DECISIONS.md + STATUS.md updated for every decision above.
