# Handoff for Claude — ZHIDAO game, Blender characters and Unity

Date: 2026-09-03  
Source repository: `C:\projects\ZHIDAO protocol`  
Unity project: `C:\projects\ZHIDAO-Campus`

## 1. The game concept

The user wants to explore a small 3D game connected to the ZHIDAO Hainan
project. The intended form is a **visual novel with light RPG and exploration
elements**, presented like a stylized PC/PS2-era game rather than a modern
realistic production.

The desired feeling is:

- low-poly 3D characters based on the user's illustrated designs;
- expressive portraits and dialogue choices;
- compact explorable campus locations;
- simple objectives, relationships, REP or other progression hooks;
- bright tropical spaces mixed with ZHIDAO's cybernetic motifs;
- intentionally limited textures, matte materials and visible polygonal form;
- early-2000s atmosphere, not photorealism and not a high-detail AAA pipeline.

The game is not intended to replace the web application. A reasonable future
role is a narrative companion: introduce characters and locations, provide
short episodes or event scenes, then optionally return outcomes to the main
ZHIDAO season system. No such web/backend synchronization exists yet.

Do not expand the game into a huge open world. The useful target is a sequence
of small, finishable episodes built from reusable characters, locations and
dialogue components.

## 2. User background and collaboration expectations

The user is new to 3D modelling and game design and chose Unity as the engine
they want to try. They need explanations in practical language and workflows
that can be reproduced without expert manual sculpting.

The user explicitly allowed modification of the Blender model during the
Architect work. Preserve earlier versions and make new numbered files instead
of overwriting approved sources. When an automated script regenerates a file,
warn that manual edits to that generated version must first be copied elsewhere.

The user repeatedly emphasized:

- the models do not need many details;
- the target is a PS1/PS2-like stylization;
- silhouette, face, symmetry and clean side views matter more than polygon
  density or realistic surface detail;
- a character must look acceptable from front, both profiles, both
  three-quarter views and back—not only from one favorable camera;
- the Architect should remain recognizable compared with the supplied 2D
  reference;
- the first character should become a practical base for creating more
  characters later.

## 3. What already exists

This is no longer only a concept. Two related bodies of work exist:

### Blender source assets in the main repository

- character work: `game_assets/architect/`
- campus environment: `game_assets/hainan_campus/`

These files are currently untracked in the main repository working tree. Do
not delete, reset, move or bulk-regenerate them without checking the exact
target and preserving the existing versions.

### Separate Unity project

`C:\projects\ZHIDAO-Campus` is a real Unity project created with Unity
**6000.3.23f1**. It is not currently a Git repository.

The project already contains:

- the imported low-poly campus;
- materials, sky and exterior collisions;
- a first-person walking controller;
- a travel/menu overlay with several destinations;
- the static Architect v16 NPC;
- a first-meeting dialogue episode;
- Windows x64 builds and QA reports.

Do not say Unity has not been started or that the campus has not been imported.
Those steps are complete.

## 4. Architect character — current source of truth

Open:

`game_assets/architect/architect-reference-v16.blend`

Do not open an earlier version and assume it updates automatically. v01–v15
remain as history and comparison sources. The latest collection is
`ARCHITECT_v16`.

The character is a static low-poly male figure based on a single frontal 2D
illustration:

- brown layered hair;
- blue eyes, short beard and moustache;
- white rolled-sleeve shirt;
- loose black tie;
- black flared trousers and black shoes;
- cybernetic neck and forearms/hands with restrained red lines;
- an optional one-sided cybernetic cheek/temple treatment.

The visual target is a clean PS2-era anime-influenced character, not a sculpted
realistic human.

### Verified v16 properties

- height: approximately **1.83163 m**;
- visible source model: approximately **12,514 triangles** with modifiers and
  laces;
- Unity export: **12,262 triangles**, 6,350 vertices;
- head, ears, hands and required closed surfaces were validated;
- no zero-area triangles in the exported geometry;
- paired anatomy and wardrobe parts are symmetrical to sub-millimetre
  tolerance; head mirror error is far below 0.001 mm;
- both hands are connected meshes with four separated finger sections plus a
  separated thumb section;
- feet share the same ground plane;
- all source images needed by the file are packed;
- the original 2D reference bitmap was not edited by the finishing scripts.

These numerical checks prove consistency, not perfect artistic likeness or
animation readiness.

## 5. Architect modelling structure

Keep the logical modules separate. The Unity export collapses source objects
into these eleven modules:

1. `Architect_v16_Belt`
2. `Architect_v16_CyberArm_L`
3. `Architect_v16_CyberArm_R`
4. `Architect_v16_CyberNeck`
5. `Architect_v16_Hair`
6. `Architect_v16_Head`
7. `Architect_v16_Shirt`
8. `Architect_v16_Shoe_L`
9. `Architect_v16_Shoe_R`
10. `Architect_v16_Tie`
11. `Architect_v16_Trousers`

In the Blender source, head, ears, hands, hair pieces, clothing, cyber parts
and hidden body fitting guides remain separately editable.

The head has neutral shape parameters:

- `Jaw_width`
- `Head_width`
- `Nose_projection`

Their default values are zero. They were introduced for controlled variations,
but they are not a complete character generator.

The optional cyber cheek can be disabled in material
`v16_Skin_and_optional_cyber_cheek` through `Cyber_cheek_enabled = 0`.

The anatomical head geometry is symmetric. Hair, beard styling and the
one-sided cybernetic treatment may be artistically asymmetric. Do not mirror
the entire appearance blindly.

## 6. How the Architect was built

The work evolved through numbered, preserved stages:

- initial procedural low-poly blockout;
- clothing, shoes and cybernetic surface passes;
- v09 reference-based reconstruction;
- v10–v12 proportion, symmetry, hands, clothes and face corrections;
- v13 real side-depth correction after the model was found too thin in
  profile;
- v14 topology/symmetry cleanup;
- v15 face likeness and UV registration correction;
- v16 final simple hair and appearance pass.

Most iterations were produced through Blender Python scripts under:

`game_assets/architect/blender/`

Important current scripts:

- `architect_finish_v16.py` — orchestrates the v16 finishing pass;
- `architect_hair_v16.py` — builds the v16 hair pieces;
- `validate_architect_v16.py` — reopens and audits the saved blend;
- `render_architect_v16_review.py` — renders standard review views;
- `compare_architect_v16.py` — produces equal-scale comparisons;
- `export_architect_v16_unity.py` — creates the portable Unity package.

`ARCHITECT_V16_FULL=1` runs the full finishing/review sequence. Diagnostic
scripts are intended to read and render; they should not silently save over
the source model.

Never deform the character to compensate for a camera angle. Correct geometry
in normal 3D coordinates and move the camera separately.

## 7. Character materials and texturing

The Blender source uses a mix of simple procedural materials and registered
colour from the supplied 2D reference. The face drawing, eyes, beard and some
surface styling are texture-driven; they are not separate facial-animation
systems.

The Unity export contains:

- `Architect_v16_BaseColor.png` — 2048×2048 complete albedo;
- `Architect_v16_Emission.png` — 2048×2048 emission;
- `Architect_v16_Surface.png` — optional roughness/metallic/weight data;
- `architect-v16-static.fbx`;
- `architect-v16-portable.blend`;
- an export manifest and validation report.

The atlas regions are divided broadly into wardrobe, cyber and head regions.
Unity must use `AtlasUV` as UV0 without tiling. Base alpha is a lighting/BSDF
weight, **not transparency**. The opaque shader contract is effectively:

```text
Base.rgb * Base.a * matteLighting + Emission.rgb
```

Do not enable alpha transparency for the base map. Do not apply an additional
vertex tint over the baked base colour.

## 8. Honest limitations of Architect v16

The current character is a finished **static appearance model**, not a fully
game-ready animated character.

Missing:

- armature/skeleton;
- skin weights;
- facial rig, visemes or eye controls;
- animation clips;
- tested deformation topology at shoulders, elbows, wrists, hips and knees;
- tested retargeting in Unity;
- LODs;
- a shared production character-builder system.

Because the only strong reference was a frontal image, profile and back views
are artistic interpretations. The face texture is intentionally low resolution
at close range. Do not solve this by adding pores or high-frequency realism;
improve silhouette, planes, UV placement and readable features first.

## 9. Reusing the character for new cast members

The user wants the Architect to become a starting point for other characters,
but v16 should not be treated as a universal finished template yet.

A safe workflow for the next character is:

1. Duplicate the latest source to a new character directory and version; never
   modify `architect-reference-v16.blend` in place.
2. Keep scale, forward axis, foot plane and broad body proportions compatible
   with Unity.
3. Decide which modules can actually be reused: hands, shoes, a hidden body
   fitting guide, or parts of clothing. Do not automatically retain the
   Architect's face texture, beard, cyber cheek or hair.
4. Replace the head texture and adjust `Jaw_width`, `Head_width` and
   `Nose_projection` only as a starting point. Substantial differences require
   real mesh edits.
5. Build new hair as a few closed, overlapping low-poly clumps around a scalp
   cap. Avoid flat floating cards, holes at the crown and long parallel strips
   at the back.
6. Create or refit clothing as separate modules. Do not stretch the white shirt
   and trousers into every costume.
7. Preserve anatomical symmetry first. Add deliberate asymmetry only to hair,
   accessories, wear, implants or texture accents.
8. Review front, back, both profiles and both three-quarter views under the
   same camera scale and lighting.
9. Validate normals, degenerates, open surfaces, ground contact, intersections,
   duplicate geometry, missing textures and transform consistency.
10. Bake a new atlas and export a new FBX/manifest pair. Never mix a new FBX
    with the Architect's old atlas.

For future characters, request at least a frontal reference and, when possible,
a profile/back or turnaround. If only one view exists, state clearly that the
unseen sides are interpretation.

A sensible per-character triangle target is roughly the same order as the
Architect—approximately 8k–15k triangles—unless hair or costume genuinely
requires more. This is a style budget, not a hard engine limit.

## 10. Rigging strategy for reusable characters

Do not rig each character ad hoc before deciding on a shared skeleton.

Recommended next character-system milestone:

1. Make a clean duplicate of the Architect and simplify hidden/intersecting
   topology where deformation requires it.
2. Build one humanoid skeleton with consistent bone names, orientation and
   rest pose.
3. Test shoulders, elbows, wrists, fingers, hips and knees with a small pose
   suite before producing more cast members.
4. Keep cyber arms compatible with the same skeleton unless a character truly
   needs mechanical articulation.
5. Export and configure Unity Humanoid only after checking that the stylized
   proportions map correctly. Generic may be safer if Humanoid retargeting
   distorts the silhouette.
6. Create a minimal shared animation set: idle, walk, run, turn, talk gesture
   and one interaction.
7. Add simple face states separately—texture swaps, eye/mouth meshes or a few
   controlled shape keys—rather than committing immediately to a complex
   facial rig.

The first rigging pass should prove reliable deformation, not add many
animations.

## 11. Hainan campus environment in Blender

Current source:

`game_assets/hainan_campus/hainan-campus-ps2-v02.blend`

v01 created a stylized coastal campus with a rounded tower, low academic
buildings, plaza, pool, roads, palms, stadium, promenade, beach, sea and distant
mountains. v02 added a residential quarter:

- four eight-storey dormitory blocks;
- central conical shop on the first level;
- gym on the second level;
- small basketball, table-tennis and exercise areas;
- broadleaf trees, flowerbeds, benches, bins, bicycle racks and lamps.

The v02 Blender validation passed with approximately 69,974 triangles before
Unity export. The Unity geometry export contains 75,282 triangles in 562
spatial/material chunks.

Important: this environment was composed from architectural and mood
references and is **artistically condensed**. It is not a survey-accurate model
of the real campus. The current web-app campus-map task is separately trying to
digitize actual geography. Do not claim the existing 3D level matches the real
map, and do not use the decorative Blender layout as authoritative GIS data.

If the game later needs a geographically faithful campus, build it as a new
version from verified map footprints instead of destructively reshaping v02.

## 12. Unity project configuration

Project root: `C:\projects\ZHIDAO-Campus`

Current technical choices:

- Unity 6000.3.23f1;
- Built-in Render Pipeline;
- Linear colour space;
- one directional light and panoramic sky;
- custom matte shaders for campus and character;
- 8× MSAA, VSync 1;
- legacy Input Manager;
- no additional gameplay framework, DI, networking framework or async package;
- namespace convention: `Zhidao.Campus`;
- small MonoBehaviour components with serialized private fields;
- Editor builders and audits under `Assets/Campus/Editor`.

The project was deliberately kept package-light. Do not add packages simply
because they are common in modern Unity projects.

## 13. Current Unity scenes and builds

Preserved walkaround scene:

`Assets/Campus/Scenes/Campus.unity`

Current startup episode:

`Assets/Campus/Scenes/CampusFirstMeeting.unity`

Current final Windows build:

`Builds/Windows-v02-FirstMeeting/ZhidaoCampus.exe`

Copy/share the complete build folder, not only the executable.

The earlier exterior walkaround passed import, build and runtime checks. It has
first-person walking, running, jumping, mouse look, respawn, exterior
collisions and travel points for plaza, dormitories, sports area, promenade and
stadium.

The authoritative general QA report is:

`C:\projects\ZHIDAO-Campus\QA\validation-report.md`

## 14. First-meeting episode

The current game contains one small episode:

1. The player starts near the plaza.
2. The static Architect stands nearby.
3. Within interaction range, `E` opens a conversation camera and dialogue.
4. Two provisional Russian response choices lead to distinct replies.
5. The objective to reach the dormitories is granted only after the chosen
   reply is acknowledged.
6. Arrival within the destination radius completes the episode.

Main code:

- `Assets/Campus/Scripts/FirstMeetingState.cs`
- `Assets/Campus/Scripts/FirstMeetingController.cs`
- editing guide: `C:\projects\ZHIDAO-Campus\Docs\FirstMeeting.md`

The state progression is:

```text
MeetArchitect → GoToDorm → Complete
```

The episode has no persistence. Restart the executable to reset the branch.
The Architect remains a static NPC without animation.

Automated evidence:

- final build succeeded with 0 errors and 0 warnings;
- dialogue smoke: 18/18 passed;
- movement regression: 16/16 passed;
- rendered captures passed at 1280×800 and 960×600.

Do not overstate manual testing: the final physical keyboard/mouse test was
interrupted before completion. The remaining checklist is in:

`C:\projects\ZHIDAO-Campus\QA\first-meeting\validation-report.md`

## 15. Generated-scene warning

The Unity scenes and character prefab are assembled by Editor builders.

`CampusFirstMeetingBuilder.AssembleAndBuild` regenerates the episode scene and
prefab from the preserved baseline. `CampusSceneBuilder` can likewise
regenerate the campus scene.

Before making manual scene or prefab edits:

- read the relevant builder;
- determine whether the asset is generated;
- save meaningful manual work to a new path or update the builder as the source
  of truth;
- do not rerun a builder that will silently erase manual changes.

The same principle applies to Blender generation scripts.

## 16. Relationship between game and web app

The web app lives in the main repository under `zhidao_v4/`. The Unity game is
a separate desktop project. They currently share design, story and assets but
not runtime state.

There is currently no:

- WebGL build embedded in `/app/`;
- API authentication from Unity;
- REP/reward synchronization;
- shared save account;
- downloadable-game launcher in the app;
- production decision about whether the game is mandatory or optional.

Possible future integration options, from smallest to largest:

1. Use rendered character scenes or short videos inside the web app.
2. Offer the Windows episode as an optional companion download.
3. Produce a constrained WebGL episode and open it from an app event.
4. Connect completed episodes to the V4 API through signed, idempotent result
   claims.

Do not begin option 4 before defining authentication, anti-replay rules and
whether game rewards affect the real seasonal economy.

## 17. Recommended next steps

For the game itself:

1. Complete the remaining manual first-meeting input/focus test.
2. Decide whether the next milestone is character animation or a second static
   dialogue episode.
3. If animation is chosen, create and validate one shared rig before modelling
   many additional characters.
4. Turn provisional first-meeting text into approved story content.
5. Add a minimal session save only after the episode structure stabilizes.
6. Keep environments small and episode-driven.

For character production:

1. Preserve Architect v16 unchanged as the visual baseline.
2. Create a separate reusable humanoid/base-character v01.
3. Test the base with one substantially different second character, not a
   recoloured Architect.
4. Establish shared skeleton, naming, scale, export and atlas conventions.
5. Document each new character with source reference, intentional
   interpretations, validation report and Unity manifest.

## 18. Safety and validation rules

- Never overwrite approved `.blend`, `.unity`, prefab or build versions without
  an explicit reason and a preserved predecessor.
- Do not use `git clean`, destructive resets or broad file deletion around
  untracked `game_assets/`.
- Do not alter Unity licensing files, proxy/security settings or install new
  packages without need.
- Do not claim static mesh validation proves rigging quality.
- Do not claim the artistic campus is geographically accurate.
- Keep character FBX and its baked atlas from the same export together.
- Preserve axis, metre scale and ground plane across Blender and Unity.
- Run visual comparisons at equal scale; do not judge likeness from differently
  framed images.
- Validate saved/reopened files, not only the in-memory Blender scene.

Core principle:

> Build a small playable story with reusable low-poly assets; do not turn a
> deliberate PS2-style experiment into an unfinished modern AAA project.
