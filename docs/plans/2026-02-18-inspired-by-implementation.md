# Inspired By Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the `inspired_by` input mode — five creative phases that analyze a source story, generate a new story inspired by its themes and style, and feed into the existing media generation pipeline.

**Architecture:** Five new functions in `story_writer.py`, each following the existing pattern (system prompt + structured output via ClaudeClient). Phase artifacts stored as JSON files on disk (not in ProjectMetadata) for human review at checkpoints. Orchestrator gets five new dispatch branches. CLI unlocks the mode and adds `--premise` flag.

**Tech Stack:** ClaudeClient (generate_structured / generate), ProjectState, JSON files for inter-phase artifacts.

**Design doc:** `docs/plans/2026-02-18-inspired-by-design.md`

**Design divergences:**
1. The design doc references `state.metadata["analysis"]` for artifact storage. However, `state.metadata` is a `ProjectMetadata` Pydantic model, not a dict. This plan uses JSON files on disk (`analysis.json`, `story_bible.json`, `outline.json`) instead. Consistent with existing patterns (scene `.md` files, `narration_flags.md`). No model changes needed.
2. The design doc says SCENE_PROSE uses `generate()` (plain text). This plan uses `generate_structured()` with a `{prose, summary}` schema instead, so the running summary is captured alongside the prose in a single call rather than requiring a separate summarization step.

---

### Task 1: CLI — Add `--premise` Flag and Unlock `inspired_by` Mode

**Files:**
- Modify: `src/story_video/cli.py:276-306` (create command)
- Test: `tests/test_cli.py`

**Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
class TestCreateInspiredByModeAccepted:
    """create command accepts inspired_by mode."""

    def test_inspired_by_mode_does_not_exit_with_not_implemented(self, tmp_path, mocker):
        """inspired_by mode should not show 'not yet implemented' error."""
        mocker.patch("story_video.cli._run_with_providers")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode", "inspired_by",
                "--source-material", "Once upon a time...",
                "--output-dir", str(tmp_path),
            ],
        )
        assert "not yet implemented" not in (result.output or "").lower()


class TestCreatePremiseFlag:
    """create command accepts --premise flag."""

    def test_premise_written_to_project_dir(self, tmp_path, mocker):
        """--premise value is written to premise.txt in the project directory."""
        mocker.patch("story_video.cli._run_with_providers")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode", "inspired_by",
                "--source-material", "Once upon a time...",
                "--premise", "set it in space",
                "--output-dir", str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        # Find the project dir (inspired_by-YYYY-MM-DD)
        project_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(project_dirs) == 1
        premise_file = project_dirs[0] / "premise.txt"
        assert premise_file.exists()
        assert premise_file.read_text() == "set it in space"

    def test_premise_ignored_for_adapt_mode(self, tmp_path, mocker, caplog):
        """--premise with adapt mode logs a warning."""
        mocker.patch("story_video.cli._run_with_providers")
        runner.invoke(
            app,
            [
                "create",
                "--mode", "adapt",
                "--source-material", "Once upon a time...",
                "--premise", "set it in space",
                "--output-dir", str(tmp_path),
            ],
        )
        # No premise.txt written
        project_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        if project_dirs:
            assert not (project_dirs[0] / "premise.txt").exists()

    def test_no_premise_no_file(self, tmp_path, mocker):
        """Without --premise, no premise.txt is created."""
        mocker.patch("story_video.cli._run_with_providers")
        runner.invoke(
            app,
            [
                "create",
                "--mode", "inspired_by",
                "--source-material", "Once upon a time...",
                "--output-dir", str(tmp_path),
            ],
        )
        project_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert len(project_dirs) == 1
        assert not (project_dirs[0] / "premise.txt").exists()


class TestCreateInspiredByRequiresSource:
    """create command requires --source-material for inspired_by mode."""

    def test_inspired_by_without_source_exits(self, tmp_path):
        """inspired_by mode without --source-material should fail."""
        result = runner.invoke(
            app,
            [
                "create",
                "--mode", "inspired_by",
                "--output-dir", str(tmp_path),
            ],
        )
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::TestCreateInspiredByModeAccepted -v`
Run: `pytest tests/test_cli.py::TestCreatePremiseFlag -v`
Run: `pytest tests/test_cli.py::TestCreateInspiredByRequiresSource -v`
Expected: FAIL — inspired_by still shows "not yet implemented", no `--premise` flag

**Step 3: Implement**

In `src/story_video/cli.py`:

1. Add `--premise` parameter to the `create` command (after `source_material`):
```python
premise: str | None = typer.Option(None, help="Optional creative direction for inspired_by mode"),
```

2. Change the mode guard (line 298-306) from blocking both `ORIGINAL` and `INSPIRED_BY` to blocking only `ORIGINAL`:
```python
if input_mode == InputMode.ORIGINAL:
    console.print(
        Panel(
            f"Mode '{mode}' is not yet implemented. Only 'adapt' and 'inspired_by' are currently supported.",
            title="Error",
            border_style="red",
        )
    )
    raise typer.Exit(1)
```

3. Add source validation for `inspired_by` (alongside existing adapt check):
```python
if input_mode in (InputMode.ADAPT, InputMode.INSPIRED_BY) and source_material is None:
    console.print(
        Panel(
            f"{mode} mode requires --source-material (path to file or inline text).",
            title="Error",
            border_style="red",
        )
    )
    raise typer.Exit(1)
```

4. After writing source_story.txt, write premise.txt if applicable:
```python
# --- Write premise (inspired_by / original modes only) ---
if premise is not None:
    if input_mode in (InputMode.INSPIRED_BY, InputMode.ORIGINAL):
        (state.project_dir / "premise.txt").write_text(premise, encoding="utf-8")
    else:
        logger.warning("--premise is only used with inspired_by or original modes; ignoring")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::TestCreateInspiredByModeAccepted tests/test_cli.py::TestCreatePremiseFlag tests/test_cli.py::TestCreateInspiredByRequiresSource -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/cli.py tests/test_cli.py
git commit -m "feat: unlock inspired_by mode and add --premise CLI flag"
```

---

### Task 2: Orchestrator — Add Creative Phase Dispatch and Checkpoints

**Files:**
- Modify: `src/story_video/pipeline/orchestrator.py:26-46,207-258`
- Test: `tests/test_orchestrator.py`

**Step 1: Write failing tests**

Add to `tests/test_orchestrator.py`:

```python
class TestDispatchCreativePhases:
    """_dispatch_phase routes creative phases to story_writer functions."""

    def test_dispatches_analysis(self, mocker):
        """ANALYSIS phase calls story_writer.analyze_source."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.analyze_source")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.ANALYSIS, state, claude_client=client,
            tts_provider=None, image_provider=None, caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_story_bible(self, mocker):
        """STORY_BIBLE phase calls story_writer.create_story_bible."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.create_story_bible")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.STORY_BIBLE, state, claude_client=client,
            tts_provider=None, image_provider=None, caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_outline(self, mocker):
        """OUTLINE phase calls story_writer.create_outline."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.create_outline")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.OUTLINE, state, claude_client=client,
            tts_provider=None, image_provider=None, caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_scene_prose(self, mocker):
        """SCENE_PROSE phase calls story_writer.write_scene_prose."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.write_scene_prose")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.SCENE_PROSE, state, claude_client=client,
            tts_provider=None, image_provider=None, caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_dispatches_critique_revision(self, mocker):
        """CRITIQUE_REVISION phase calls story_writer.critique_and_revise."""
        mock_fn = mocker.patch("story_video.pipeline.orchestrator.critique_and_revise")
        state = MagicMock()
        client = MagicMock()
        _dispatch_phase(
            PipelinePhase.CRITIQUE_REVISION, state, claude_client=client,
            tts_provider=None, image_provider=None, caption_provider=None,
        )
        mock_fn.assert_called_once_with(state, client)

    def test_creative_phases_require_claude_client(self):
        """All creative phases raise ValueError when claude_client is None."""
        state = MagicMock()
        for phase in [
            PipelinePhase.ANALYSIS,
            PipelinePhase.STORY_BIBLE,
            PipelinePhase.OUTLINE,
            PipelinePhase.SCENE_PROSE,
            PipelinePhase.CRITIQUE_REVISION,
        ]:
            with pytest.raises(ValueError, match="claude_client is required"):
                _dispatch_phase(
                    phase, state, claude_client=None,
                    tts_provider=None, image_provider=None, caption_provider=None,
                )
```

Also add a test that the creative phases are in `_CHECKPOINT_PHASES`:

```python
class TestCreativePhasesAreCheckpoints:
    """All five creative phases are checkpoint phases."""

    def test_creative_phases_in_checkpoint_set(self):
        """ANALYSIS through CRITIQUE_REVISION are all checkpoint phases."""
        from story_video.pipeline.orchestrator import _CHECKPOINT_PHASES
        assert PipelinePhase.ANALYSIS in _CHECKPOINT_PHASES
        assert PipelinePhase.STORY_BIBLE in _CHECKPOINT_PHASES
        assert PipelinePhase.OUTLINE in _CHECKPOINT_PHASES
        assert PipelinePhase.SCENE_PROSE in _CHECKPOINT_PHASES
        assert PipelinePhase.CRITIQUE_REVISION in _CHECKPOINT_PHASES
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator.py::TestDispatchCreativePhases -v`
Run: `pytest tests/test_orchestrator.py::TestCreativePhasesAreCheckpoints -v`
Expected: FAIL — phases not dispatched, not in checkpoint set

**Step 3: Implement**

In `src/story_video/pipeline/orchestrator.py`:

1. Update import (line 26):
```python
from story_video.pipeline.story_writer import (
    analyze_source,
    create_outline,
    create_story_bible,
    critique_and_revise,
    flag_narration,
    split_scenes,
    write_scene_prose,
)
```

2. Add creative phases to `_CHECKPOINT_PHASES` (line 39-46):
```python
_CHECKPOINT_PHASES = frozenset(
    {
        PipelinePhase.ANALYSIS,
        PipelinePhase.STORY_BIBLE,
        PipelinePhase.OUTLINE,
        PipelinePhase.SCENE_PROSE,
        PipelinePhase.CRITIQUE_REVISION,
        PipelinePhase.SCENE_SPLITTING,
        PipelinePhase.NARRATION_FLAGGING,
        PipelinePhase.IMAGE_PROMPTS,
        PipelinePhase.NARRATION_PREP,
    }
)
```

3. Add dispatch branches in `_dispatch_phase` (before the `else` clause at line 256):
```python
elif phase == PipelinePhase.ANALYSIS:
    if claude_client is None:
        msg = "claude_client is required for ANALYSIS phase"
        raise ValueError(msg)
    analyze_source(state, claude_client)

elif phase == PipelinePhase.STORY_BIBLE:
    if claude_client is None:
        msg = "claude_client is required for STORY_BIBLE phase"
        raise ValueError(msg)
    create_story_bible(state, claude_client)

elif phase == PipelinePhase.OUTLINE:
    if claude_client is None:
        msg = "claude_client is required for OUTLINE phase"
        raise ValueError(msg)
    create_outline(state, claude_client)

elif phase == PipelinePhase.SCENE_PROSE:
    if claude_client is None:
        msg = "claude_client is required for SCENE_PROSE phase"
        raise ValueError(msg)
    write_scene_prose(state, claude_client)

elif phase == PipelinePhase.CRITIQUE_REVISION:
    if claude_client is None:
        msg = "claude_client is required for CRITIQUE_REVISION phase"
        raise ValueError(msg)
    critique_and_revise(state, claude_client)
```

Note: The five new functions must exist (even as stubs) for the import to work. Add stubs to `story_writer.py` at the end of the public API section:

```python
def analyze_source(state: ProjectState, client: ClaudeClient) -> None:
    """Analyze source material to extract craft notes and thematic brief."""
    raise NotImplementedError("analyze_source not yet implemented")


def create_story_bible(state: ProjectState, client: ClaudeClient) -> None:
    """Create story bible with characters, setting, and world rules."""
    raise NotImplementedError("create_story_bible not yet implemented")


def create_outline(state: ProjectState, client: ClaudeClient) -> None:
    """Create scene-by-scene outline with beats and word targets."""
    raise NotImplementedError("create_outline not yet implemented")


def write_scene_prose(state: ProjectState, client: ClaudeClient) -> None:
    """Write prose for each scene from the outline."""
    raise NotImplementedError("write_scene_prose not yet implemented")


def critique_and_revise(state: ProjectState, client: ClaudeClient) -> None:
    """Review and revise each scene's prose in a single pass."""
    raise NotImplementedError("critique_and_revise not yet implemented")
```

Update `__all__` in `story_writer.py`:
```python
__all__ = [
    "analyze_source",
    "create_outline",
    "create_story_bible",
    "critique_and_revise",
    "flag_narration",
    "split_scenes",
    "write_scene_prose",
]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py::TestDispatchCreativePhases tests/test_orchestrator.py::TestCreativePhasesAreCheckpoints -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/pipeline/orchestrator.py src/story_video/pipeline/story_writer.py tests/test_orchestrator.py
git commit -m "feat: wire creative phase dispatch and checkpoints in orchestrator"
```

---

### Task 3: Implement `analyze_source()`

**Files:**
- Modify: `src/story_video/pipeline/story_writer.py`
- Test: `tests/test_story_writer.py`

**Step 1: Write failing tests**

Add to `tests/test_story_writer.py`:

```python
# ---------------------------------------------------------------------------
# Analysis phase — test data
# ---------------------------------------------------------------------------

ANALYSIS_RESPONSE = {
    "craft_notes": {
        "sentence_structure": "Short declarative sentences.",
        "vocabulary": "Simple, concrete nouns.",
        "tone": "Dry, understated.",
        "pacing": "Slow openings.",
        "narrative_voice": "Third person limited, past tense.",
    },
    "thematic_brief": {
        "themes": ["isolation", "duty"],
        "emotional_arc": "Resignation to acceptance",
        "central_tension": "Bound to a place",
        "mood": "Melancholic",
    },
    "source_stats": {
        "word_count": 90,
        "scene_count_estimate": 3,
    },
}


# ---------------------------------------------------------------------------
# Analysis phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def analysis_client():
    """Mock ClaudeClient for analysis phase."""
    client = MagicMock()
    client.generate_structured.return_value = ANALYSIS_RESPONSE
    return client


@pytest.fixture()
def inspired_state(tmp_path):
    """Create a project state in inspired_by mode with source_story.txt."""
    state = ProjectState.create(
        project_id="inspired-test",
        mode=InputMode.INSPIRED_BY,
        config=AppConfig(),
        output_dir=tmp_path,
    )
    source = tmp_path / "inspired-test" / "source_story.txt"
    source.write_text(SOURCE_TEXT)
    return state


# ---------------------------------------------------------------------------
# Analysis phase — tests
# ---------------------------------------------------------------------------


class TestAnalyzeSourceCallsClaude:
    """analyze_source() sends source material to Claude."""

    def test_source_text_in_user_message(self, inspired_state, analysis_client):
        """Source material is included in the user message to Claude."""
        analyze_source(inspired_state, analysis_client)

        call_kwargs = analysis_client.generate_structured.call_args.kwargs
        assert SOURCE_TEXT in call_kwargs["user_message"]


class TestAnalyzeSourceWritesJson:
    """analyze_source() writes analysis.json to project directory."""

    def test_analysis_json_written(self, inspired_state, analysis_client):
        """analysis.json exists after call and contains expected keys."""
        analyze_source(inspired_state, analysis_client)

        analysis_path = inspired_state.project_dir / "analysis.json"
        assert analysis_path.exists()
        data = json.loads(analysis_path.read_text())
        assert "craft_notes" in data
        assert "thematic_brief" in data
        assert "source_stats" in data


class TestAnalyzeSourceCraftNotes:
    """analyze_source() stores craft notes with all required fields."""

    def test_craft_notes_fields(self, inspired_state, analysis_client):
        """Craft notes contain sentence_structure, vocabulary, tone, pacing, narrative_voice."""
        analyze_source(inspired_state, analysis_client)

        data = json.loads((inspired_state.project_dir / "analysis.json").read_text())
        craft = data["craft_notes"]
        assert "sentence_structure" in craft
        assert "vocabulary" in craft
        assert "tone" in craft
        assert "pacing" in craft
        assert "narrative_voice" in craft


class TestAnalyzeSourceThematicBrief:
    """analyze_source() stores thematic brief with all required fields."""

    def test_thematic_brief_fields(self, inspired_state, analysis_client):
        """Thematic brief contains themes, emotional_arc, central_tension, mood."""
        analyze_source(inspired_state, analysis_client)

        data = json.loads((inspired_state.project_dir / "analysis.json").read_text())
        brief = data["thematic_brief"]
        assert "themes" in brief
        assert "emotional_arc" in brief
        assert "central_tension" in brief
        assert "mood" in brief


class TestAnalyzeSourceStats:
    """analyze_source() captures source dimensions."""

    def test_source_stats_present(self, inspired_state, analysis_client):
        """Source stats contain word_count and scene_count_estimate."""
        analyze_source(inspired_state, analysis_client)

        data = json.loads((inspired_state.project_dir / "analysis.json").read_text())
        stats = data["source_stats"]
        assert "word_count" in stats
        assert "scene_count_estimate" in stats


class TestAnalyzeSourceMissingFile:
    """analyze_source() raises FileNotFoundError when source_story.txt is missing."""

    def test_missing_source_raises(self, tmp_path, analysis_client):
        """No source_story.txt raises FileNotFoundError."""
        state = ProjectState.create(
            project_id="no-source",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        with pytest.raises(FileNotFoundError, match="source_story.txt"):
            analyze_source(state, analysis_client)


class TestAnalyzeSourceSavesState:
    """analyze_source() persists state."""

    def test_state_saved(self, inspired_state, analysis_client):
        """state.save() is called after analysis."""
        analyze_source(inspired_state, analysis_client)

        reloaded = ProjectState.load(inspired_state.project_dir)
        assert reloaded.metadata.project_id == "inspired-test"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_story_writer.py::TestAnalyzeSourceCallsClaude -v`
Expected: FAIL — `analyze_source` raises `NotImplementedError`

**Step 3: Implement**

In `src/story_video/pipeline/story_writer.py`, add constants and replace the stub:

```python
import json

# ... after existing constants ...

ANALYSIS_SYSTEM = (
    "You are a literary analyst examining a story to extract its writing style"
    " and thematic essence.\n\n"
    "Your goal is to capture two things:\n"
    "1. CRAFT NOTES — How the story is written. Concrete observations about"
    " sentence structure, vocabulary choices, tone, pacing, and narrative voice."
    " Be specific: quote patterns, note tendencies, describe rhythms.\n"
    "2. THEMATIC BRIEF — What the story is about at a deeper level. Themes,"
    " emotional arc, central tension, overall mood.\n"
    "3. SOURCE STATS — Word count and estimated number of natural scenes.\n\n"
    "This analysis will be used to write a NEW, completely different story"
    " that captures the same feel. Focus on transferable qualities, not"
    " plot-specific details."
)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "craft_notes": {
            "type": "object",
            "properties": {
                "sentence_structure": {"type": "string"},
                "vocabulary": {"type": "string"},
                "tone": {"type": "string"},
                "pacing": {"type": "string"},
                "narrative_voice": {"type": "string"},
            },
            "required": [
                "sentence_structure",
                "vocabulary",
                "tone",
                "pacing",
                "narrative_voice",
            ],
        },
        "thematic_brief": {
            "type": "object",
            "properties": {
                "themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "emotional_arc": {"type": "string"},
                "central_tension": {"type": "string"},
                "mood": {"type": "string"},
            },
            "required": ["themes", "emotional_arc", "central_tension", "mood"],
        },
        "source_stats": {
            "type": "object",
            "properties": {
                "word_count": {"type": "integer"},
                "scene_count_estimate": {"type": "integer"},
            },
            "required": ["word_count", "scene_count_estimate"],
        },
    },
    "required": ["craft_notes", "thematic_brief", "source_stats"],
}


def analyze_source(state: ProjectState, client: ClaudeClient) -> None:
    """Analyze source material to extract craft notes and thematic brief.

    Reads source_story.txt, sends it to Claude for analysis, and writes
    the result to analysis.json in the project directory.

    Args:
        state: Project state (must be in inspired_by mode).
        client: Claude API client.

    Raises:
        FileNotFoundError: If source_story.txt doesn't exist.
    """
    source_path = state.project_dir / "source_story.txt"
    if not source_path.exists():
        msg = f"source_story.txt not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    source_text = source_path.read_text(encoding="utf-8")

    # Strip YAML front matter if present
    _, body_text = parse_story_header(source_text)

    result = client.generate_structured(
        system=ANALYSIS_SYSTEM,
        user_message=body_text,
        tool_name="analyze_source",
        tool_schema=ANALYSIS_SCHEMA,
    )

    # Write analysis.json
    analysis_path = state.project_dir / "analysis.json"
    analysis_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    state.save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_story_writer.py -k "AnalyzeSource" -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/pipeline/story_writer.py tests/test_story_writer.py
git commit -m "feat: implement analyze_source phase for inspired_by mode"
```

---

### Task 4: Implement `create_story_bible()`

**Files:**
- Modify: `src/story_video/pipeline/story_writer.py`
- Test: `tests/test_story_writer.py`

**Step 1: Write failing tests**

Add to `tests/test_story_writer.py`:

```python
# ---------------------------------------------------------------------------
# Story bible phase — test data
# ---------------------------------------------------------------------------

BIBLE_RESPONSE = {
    "characters": [
        {
            "name": "Maren",
            "role": "protagonist",
            "description": "A quiet woman in her fifties. Weathered hands, sharp eyes.",
            "arc": "Resignation to cautious hope",
        },
    ],
    "setting": {
        "place": "A remote island lighthouse",
        "time_period": "1970s",
        "atmosphere": "Grey, salt-weathered, isolated",
    },
    "premise": "A lighthouse keeper receives an unexpected visitor.",
    "rules": ["No magic or supernatural elements"],
}


# ---------------------------------------------------------------------------
# Story bible phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bible_client():
    """Mock ClaudeClient for story bible phase."""
    client = MagicMock()
    client.generate_structured.return_value = BIBLE_RESPONSE
    return client


@pytest.fixture()
def state_with_analysis(inspired_state, analysis_client):
    """State with analysis.json already written."""
    analyze_source(inspired_state, analysis_client)
    return inspired_state


# ---------------------------------------------------------------------------
# Story bible phase — tests
# ---------------------------------------------------------------------------


class TestCreateStoryBibleCallsClaude:
    """create_story_bible() sends analysis context to Claude."""

    def test_craft_notes_in_context(self, state_with_analysis, bible_client):
        """Craft notes from analysis are included in the user message."""
        create_story_bible(state_with_analysis, bible_client)

        call_kwargs = bible_client.generate_structured.call_args.kwargs
        assert "sentence_structure" in call_kwargs["user_message"]
        assert "Short declarative" in call_kwargs["user_message"]


class TestCreateStoryBibleWritesJson:
    """create_story_bible() writes story_bible.json."""

    def test_bible_json_written(self, state_with_analysis, bible_client):
        """story_bible.json exists and contains characters and setting."""
        create_story_bible(state_with_analysis, bible_client)

        bible_path = state_with_analysis.project_dir / "story_bible.json"
        assert bible_path.exists()
        data = json.loads(bible_path.read_text())
        assert "characters" in data
        assert "setting" in data
        assert "premise" in data


class TestCreateStoryBibleWithPremise:
    """create_story_bible() includes premise hint when premise.txt exists."""

    def test_premise_in_user_message(self, state_with_analysis, bible_client):
        """premise.txt content is included in the user message."""
        (state_with_analysis.project_dir / "premise.txt").write_text("set it in space")
        create_story_bible(state_with_analysis, bible_client)

        call_kwargs = bible_client.generate_structured.call_args.kwargs
        assert "set it in space" in call_kwargs["user_message"]

    def test_no_premise_file_still_works(self, state_with_analysis, bible_client):
        """Without premise.txt, bible creation still works."""
        create_story_bible(state_with_analysis, bible_client)

        bible_path = state_with_analysis.project_dir / "story_bible.json"
        assert bible_path.exists()


class TestCreateStoryBibleMissingAnalysis:
    """create_story_bible() raises when analysis.json is missing."""

    def test_missing_analysis_raises(self, inspired_state, bible_client):
        """No analysis.json raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="analysis.json"):
            create_story_bible(inspired_state, bible_client)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_story_writer.py -k "StoryBible" -v`
Expected: FAIL — `create_story_bible` raises `NotImplementedError`

**Step 3: Implement**

In `src/story_video/pipeline/story_writer.py`:

```python
STORY_BIBLE_SYSTEM = (
    "You are creating the foundation for a new, original story.\n\n"
    "Use the thematic brief as inspiration — same emotional territory,"
    " completely different characters and world. The craft notes describe"
    " the writing style you will use later.\n\n"
    "Create:\n"
    "- Characters: name, role (protagonist/antagonist/supporting),"
    " physical and personality description (2-3 sentences), emotional arc\n"
    "- Setting: place, time period, atmosphere\n"
    "- Premise: one-paragraph story summary\n"
    "- Rules: world-building constraints (e.g. 'no magic')\n\n"
    "Keep it compact — this context is included in every subsequent API call."
)

STORY_BIBLE_SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {
                        "type": "string",
                        "enum": ["protagonist", "antagonist", "supporting"],
                    },
                    "description": {"type": "string"},
                    "arc": {"type": "string"},
                },
                "required": ["name", "role", "description", "arc"],
            },
            "minItems": 1,
        },
        "setting": {
            "type": "object",
            "properties": {
                "place": {"type": "string"},
                "time_period": {"type": "string"},
                "atmosphere": {"type": "string"},
            },
            "required": ["place", "time_period", "atmosphere"],
        },
        "premise": {"type": "string"},
        "rules": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["characters", "setting", "premise", "rules"],
}


def create_story_bible(state: ProjectState, client: ClaudeClient) -> None:
    """Create story bible with characters, setting, and world rules.

    Reads analysis.json for craft notes and thematic brief. Optionally
    reads premise.txt for user creative direction. Writes story_bible.json.

    Args:
        state: Project state.
        client: Claude API client.

    Raises:
        FileNotFoundError: If analysis.json doesn't exist.
    """
    analysis_path = state.project_dir / "analysis.json"
    if not analysis_path.exists():
        msg = f"analysis.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    # Build user message
    parts = [
        "## Craft Notes\n",
        json.dumps(analysis["craft_notes"], indent=2),
        "\n## Thematic Brief\n",
        json.dumps(analysis["thematic_brief"], indent=2),
    ]

    # Optional premise
    premise_path = state.project_dir / "premise.txt"
    if premise_path.exists():
        premise = premise_path.read_text(encoding="utf-8").strip()
        if premise:
            parts.append(f"\n## Author Direction\n\nThe author has requested: '{premise}'")

    user_message = "\n".join(parts)

    result = client.generate_structured(
        system=STORY_BIBLE_SYSTEM,
        user_message=user_message,
        tool_name="create_story_bible",
        tool_schema=STORY_BIBLE_SCHEMA,
    )

    bible_path = state.project_dir / "story_bible.json"
    bible_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    state.save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_story_writer.py -k "StoryBible" -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/pipeline/story_writer.py tests/test_story_writer.py
git commit -m "feat: implement create_story_bible phase for inspired_by mode"
```

---

### Task 5: Implement `create_outline()`

**Files:**
- Modify: `src/story_video/pipeline/story_writer.py`
- Test: `tests/test_story_writer.py`

**Step 1: Write failing tests**

Add to `tests/test_story_writer.py`:

```python
# ---------------------------------------------------------------------------
# Outline phase — test data
# ---------------------------------------------------------------------------

OUTLINE_RESPONSE = {
    "scenes": [
        {"scene_number": 1, "title": "The Arrival", "beat": "Maren steps off the ferry.", "target_words": 300},
        {"scene_number": 2, "title": "The Stranger", "beat": "A visitor appears.", "target_words": 350},
        {"scene_number": 3, "title": "The Storm", "beat": "A storm forces them together.", "target_words": 250},
    ],
    "total_target_words": 900,
}


# ---------------------------------------------------------------------------
# Outline phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def outline_client():
    """Mock ClaudeClient for outline phase."""
    client = MagicMock()
    client.generate_structured.return_value = OUTLINE_RESPONSE
    return client


@pytest.fixture()
def state_with_bible(state_with_analysis, bible_client):
    """State with both analysis.json and story_bible.json."""
    create_story_bible(state_with_analysis, bible_client)
    return state_with_analysis


# ---------------------------------------------------------------------------
# Outline phase — tests
# ---------------------------------------------------------------------------


class TestCreateOutlineCallsClaude:
    """create_outline() sends bible and analysis to Claude."""

    def test_bible_in_context(self, state_with_bible, outline_client):
        """Story bible is included in the user message."""
        create_outline(state_with_bible, outline_client)

        call_kwargs = outline_client.generate_structured.call_args.kwargs
        assert "Maren" in call_kwargs["user_message"]


class TestCreateOutlineWritesJson:
    """create_outline() writes outline.json."""

    def test_outline_json_written(self, state_with_bible, outline_client):
        """outline.json exists and contains scenes array."""
        create_outline(state_with_bible, outline_client)

        outline_path = state_with_bible.project_dir / "outline.json"
        assert outline_path.exists()
        data = json.loads(outline_path.read_text())
        assert "scenes" in data
        assert len(data["scenes"]) == 3
        assert "total_target_words" in data


class TestCreateOutlineSceneBeats:
    """create_outline() scenes have required fields."""

    def test_scene_beat_fields(self, state_with_bible, outline_client):
        """Each scene beat has scene_number, title, beat, target_words."""
        create_outline(state_with_bible, outline_client)

        data = json.loads((state_with_bible.project_dir / "outline.json").read_text())
        scene = data["scenes"][0]
        assert "scene_number" in scene
        assert "title" in scene
        assert "beat" in scene
        assert "target_words" in scene


class TestCreateOutlineSourceStats:
    """create_outline() includes source stats for length targeting."""

    def test_source_stats_in_context(self, state_with_bible, outline_client):
        """Source word count and scene estimate are in the user message."""
        create_outline(state_with_bible, outline_client)

        call_kwargs = outline_client.generate_structured.call_args.kwargs
        # source_stats from ANALYSIS_RESPONSE: word_count=90, scene_count_estimate=3
        assert "90" in call_kwargs["user_message"]


class TestCreateOutlineMissingBible:
    """create_outline() raises when story_bible.json is missing."""

    def test_missing_bible_raises(self, state_with_analysis, outline_client):
        """No story_bible.json raises FileNotFoundError."""
        # state_with_analysis has analysis.json but not story_bible.json
        with pytest.raises(FileNotFoundError, match="story_bible.json"):
            create_outline(state_with_analysis, outline_client)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_story_writer.py -k "Outline" -v`
Expected: FAIL — `create_outline` raises `NotImplementedError`

**Step 3: Implement**

In `src/story_video/pipeline/story_writer.py`:

```python
OUTLINE_SYSTEM = (
    "You are a story architect creating a scene-by-scene outline.\n\n"
    "Based on the story bible and craft notes, design the structure of"
    " the story. Each scene beat should be 1-2 sentences describing"
    " what happens — not how it's written.\n\n"
    "Rules:\n"
    "- Target the specified total word count and scene count\n"
    "- Word targets per scene are advisory — use proportion to convey"
    " importance (climactic scenes get more words, transitions get fewer)\n"
    "- Each beat describes WHAT happens, not HOW it's written\n"
    "- Scene titles should be short (3-6 words)"
)

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_number": {"type": "integer"},
                    "title": {"type": "string"},
                    "beat": {"type": "string"},
                    "target_words": {"type": "integer"},
                },
                "required": ["scene_number", "title", "beat", "target_words"],
            },
            "minItems": 1,
        },
        "total_target_words": {"type": "integer"},
    },
    "required": ["scenes", "total_target_words"],
}


def create_outline(state: ProjectState, client: ClaudeClient) -> None:
    """Create scene-by-scene outline with beats and word targets.

    Reads analysis.json and story_bible.json. Uses source_stats to
    target matching length. Writes outline.json.

    Args:
        state: Project state.
        client: Claude API client.

    Raises:
        FileNotFoundError: If analysis.json or story_bible.json is missing.
    """
    analysis_path = state.project_dir / "analysis.json"
    if not analysis_path.exists():
        msg = f"analysis.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    bible_path = state.project_dir / "story_bible.json"
    if not bible_path.exists():
        msg = f"story_bible.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    bible = json.loads(bible_path.read_text(encoding="utf-8"))

    source_stats = analysis["source_stats"]
    word_count = source_stats["word_count"]
    scene_count = source_stats["scene_count_estimate"]

    parts = [
        "## Craft Notes\n",
        json.dumps(analysis["craft_notes"], indent=2),
        "\n## Thematic Brief\n",
        json.dumps(analysis["thematic_brief"], indent=2),
        "\n## Story Bible\n",
        json.dumps(bible, indent=2),
        f"\n## Length Target\n",
        f"Target approximately {word_count} total words across approximately {scene_count} scenes.",
    ]
    user_message = "\n".join(parts)

    result = client.generate_structured(
        system=OUTLINE_SYSTEM,
        user_message=user_message,
        tool_name="create_outline",
        tool_schema=OUTLINE_SCHEMA,
    )

    outline_path = state.project_dir / "outline.json"
    outline_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    state.save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_story_writer.py -k "Outline" -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/pipeline/story_writer.py tests/test_story_writer.py
git commit -m "feat: implement create_outline phase for inspired_by mode"
```

---

### Task 6: Implement `write_scene_prose()`

**Files:**
- Modify: `src/story_video/pipeline/story_writer.py`
- Test: `tests/test_story_writer.py`

**Step 1: Write failing tests**

Add to `tests/test_story_writer.py`:

```python
# ---------------------------------------------------------------------------
# Scene prose phase — test data
# ---------------------------------------------------------------------------

PROSE_RESPONSE_1 = {
    "prose": "Maren stepped off the ferry onto the wet stones.",
    "summary": "Maren arrives on the island and sees the lighthouse.",
}

PROSE_RESPONSE_2 = {
    "prose": "The stranger stood at the door, rain dripping from his coat.",
    "summary": "A stranger appears at the lighthouse door during the storm.",
}

PROSE_RESPONSE_3 = {
    "prose": "The storm rattled the windows as they sat in silence.",
    "summary": "Maren and the stranger wait out the storm together.",
}


# ---------------------------------------------------------------------------
# Scene prose phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prose_client():
    """Mock ClaudeClient for scene prose phase."""
    client = MagicMock()
    client.generate_structured.side_effect = [
        PROSE_RESPONSE_1,
        PROSE_RESPONSE_2,
        PROSE_RESPONSE_3,
    ]
    return client


@pytest.fixture()
def state_with_outline(state_with_bible, outline_client):
    """State with analysis.json, story_bible.json, and outline.json."""
    create_outline(state_with_bible, outline_client)
    return state_with_bible


# ---------------------------------------------------------------------------
# Scene prose phase — tests
# ---------------------------------------------------------------------------


class TestWriteSceneProseCreatesScenes:
    """write_scene_prose() creates scenes in state."""

    def test_scenes_created(self, state_with_outline, prose_client):
        """One scene created per outline beat."""
        write_scene_prose(state_with_outline, prose_client)

        assert len(state_with_outline.metadata.scenes) == 3


class TestWriteSceneProseContent:
    """write_scene_prose() stores correct prose in each scene."""

    def test_scene_prose_matches_response(self, state_with_outline, prose_client):
        """Scene prose matches Claude response."""
        write_scene_prose(state_with_outline, prose_client)

        scenes = state_with_outline.metadata.scenes
        assert scenes[0].prose == PROSE_RESPONSE_1["prose"]
        assert scenes[1].prose == PROSE_RESPONSE_2["prose"]
        assert scenes[2].prose == PROSE_RESPONSE_3["prose"]


class TestWriteSceneProseCallsPerScene:
    """write_scene_prose() makes one Claude call per outline scene."""

    def test_one_call_per_scene(self, state_with_outline, prose_client):
        """Claude called once per scene beat."""
        write_scene_prose(state_with_outline, prose_client)

        assert prose_client.generate_structured.call_count == 3


class TestWriteSceneProseRunningSummary:
    """write_scene_prose() includes running summary in subsequent calls."""

    def test_second_call_includes_prior_summary(self, state_with_outline, prose_client):
        """Second scene call includes summary of first scene."""
        write_scene_prose(state_with_outline, prose_client)

        # First call should not have prior summary
        first_call = prose_client.generate_structured.call_args_list[0].kwargs
        assert "Previously:" not in first_call["user_message"]

        # Second call should include first scene's summary
        second_call = prose_client.generate_structured.call_args_list[1].kwargs
        assert PROSE_RESPONSE_1["summary"] in second_call["user_message"]


class TestWriteSceneProseWritesMdFiles:
    """write_scene_prose() writes scene .md files."""

    def test_md_files_created(self, state_with_outline, prose_client):
        """scenes/*.md files are written for each scene."""
        write_scene_prose(state_with_outline, prose_client)

        scenes_dir = state_with_outline.project_dir / "scenes"
        assert (scenes_dir / "scene_001.md").exists()
        assert (scenes_dir / "scene_002.md").exists()
        assert (scenes_dir / "scene_003.md").exists()


class TestWriteSceneProseAssetStatus:
    """write_scene_prose() sets TEXT asset to COMPLETED."""

    def test_text_asset_completed(self, state_with_outline, prose_client):
        """TEXT asset status is COMPLETED for each scene."""
        write_scene_prose(state_with_outline, prose_client)

        for scene in state_with_outline.metadata.scenes:
            assert scene.asset_status.text == SceneStatus.COMPLETED


class TestWriteSceneProseResume:
    """write_scene_prose() skips already-created scenes on resume."""

    def test_resume_skips_completed_scenes(self, state_with_outline, prose_client):
        """With scene 1 already added, only scenes 2 and 3 are processed."""
        # Manually add scene 1
        state_with_outline.add_scene(1, "The Arrival", "Pre-existing prose.")
        state_with_outline.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state_with_outline.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        # Only 2 calls needed now
        prose_client.generate_structured.side_effect = [
            PROSE_RESPONSE_2,
            PROSE_RESPONSE_3,
        ]

        write_scene_prose(state_with_outline, prose_client)

        assert len(state_with_outline.metadata.scenes) == 3
        # Scene 1 prose unchanged
        assert state_with_outline.metadata.scenes[0].prose == "Pre-existing prose."
        # Scenes 2 and 3 from Claude
        assert state_with_outline.metadata.scenes[1].prose == PROSE_RESPONSE_2["prose"]
        assert prose_client.generate_structured.call_count == 2


class TestWriteSceneProseMissingOutline:
    """write_scene_prose() raises when outline.json is missing."""

    def test_missing_outline_raises(self, state_with_bible, prose_client):
        """No outline.json raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="outline.json"):
            write_scene_prose(state_with_bible, prose_client)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_story_writer.py -k "SceneProse" -v`
Expected: FAIL — `write_scene_prose` raises `NotImplementedError`

**Step 3: Implement**

In `src/story_video/pipeline/story_writer.py`:

```python
SCENE_PROSE_SYSTEM = (
    "You are a fiction writer crafting a scene for a story.\n\n"
    "Match the writing style described in the craft notes exactly."
    " Stay faithful to the story bible. Follow the beat — don't add"
    " plot points or skip them.\n\n"
    "Return the scene prose and a 2-3 sentence summary of what happens"
    " in this scene (the summary will be used as context for writing"
    " subsequent scenes)."
)

SCENE_PROSE_SCHEMA = {
    "type": "object",
    "properties": {
        "prose": {
            "type": "string",
            "description": "The full scene prose text",
        },
        "summary": {
            "type": "string",
            "description": "2-3 sentence summary of what happens in this scene",
        },
    },
    "required": ["prose", "summary"],
}


def write_scene_prose(state: ProjectState, client: ClaudeClient) -> None:
    """Write prose for each scene from the outline.

    Reads analysis.json, story_bible.json, and outline.json. For each
    outline beat, generates prose via Claude. Maintains a running summary
    so later scenes have context of what came before.

    Creates scenes via state.add_scene() and writes .md files. Supports
    resume — skips scenes that already exist in state.

    Args:
        state: Project state.
        client: Claude API client.

    Raises:
        FileNotFoundError: If required artifact files are missing.
    """
    analysis_path = state.project_dir / "analysis.json"
    if not analysis_path.exists():
        msg = f"analysis.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    bible_path = state.project_dir / "story_bible.json"
    if not bible_path.exists():
        msg = f"story_bible.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    bible = json.loads(bible_path.read_text(encoding="utf-8"))

    outline_path = state.project_dir / "outline.json"
    if not outline_path.exists():
        msg = f"outline.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    outline = json.loads(outline_path.read_text(encoding="utf-8"))

    # Determine which scenes already exist (for resume)
    existing_scene_numbers = {s.scene_number for s in state.metadata.scenes}

    # Shared context
    craft_notes_text = json.dumps(analysis["craft_notes"], indent=2)
    bible_text = json.dumps(bible, indent=2)
    outline_text = json.dumps(outline["scenes"], indent=2)

    running_summary: list[str] = []
    scenes_dir = state.project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)

    for beat in outline["scenes"]:
        scene_num = beat["scene_number"]

        if scene_num in existing_scene_numbers:
            # Scene already created (resume). Still need its summary for context.
            existing = next(s for s in state.metadata.scenes if s.scene_number == scene_num)
            running_summary.append(f"Scene {scene_num}: {existing.title}")
            continue

        # Build user message
        parts = [
            "## Craft Notes\n",
            craft_notes_text,
            "\n## Story Bible\n",
            bible_text,
            "\n## Full Outline\n",
            outline_text,
        ]

        if running_summary:
            parts.append("\n## Previously:\n")
            parts.append("\n".join(running_summary))

        parts.append(f"\n## Current Scene: {beat['title']}\n")
        parts.append(f"Beat: {beat['beat']}")
        parts.append(f"Target: ~{beat['target_words']} words")

        user_message = "\n".join(parts)

        result = client.generate_structured(
            system=SCENE_PROSE_SYSTEM,
            user_message=user_message,
            tool_name="write_scene",
            tool_schema=SCENE_PROSE_SCHEMA,
        )

        # Create scene in state
        state.add_scene(scene_num, beat["title"], result["prose"])
        state.update_scene_asset(scene_num, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(scene_num, AssetType.TEXT, SceneStatus.COMPLETED)

        # Write .md file
        filename = f"scene_{scene_num:03d}.md"
        content = f"# Scene {scene_num}: {beat['title']}\n\n{result['prose']}\n"
        (scenes_dir / filename).write_text(content, encoding="utf-8")

        # Add summary for next scene's context
        running_summary.append(f"Scene {scene_num} ({beat['title']}): {result['summary']}")

    state.save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_story_writer.py -k "SceneProse" -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/pipeline/story_writer.py tests/test_story_writer.py
git commit -m "feat: implement write_scene_prose phase for inspired_by mode"
```

---

### Task 7: Implement `critique_and_revise()`

**Files:**
- Modify: `src/story_video/pipeline/story_writer.py`
- Test: `tests/test_story_writer.py`

**Step 1: Write failing tests**

Add to `tests/test_story_writer.py`:

```python
# ---------------------------------------------------------------------------
# Critique/revision phase — test data
# ---------------------------------------------------------------------------

CRITIQUE_RESPONSE_1 = {
    "revised_prose": "Maren stepped off the ferry onto wet stones. The lighthouse waited.",
    "changes": ["Shortened the opening — removed redundant description"],
}

CRITIQUE_RESPONSE_2 = {
    "revised_prose": "A stranger stood at the door. Rain dripped from his coat.",
    "changes": ["Split compound sentence for pacing consistency with craft notes"],
}

CRITIQUE_RESPONSE_3 = {
    "revised_prose": "The storm shook the windows. They sat without speaking.",
    "changes": ["Replaced 'rattled' with 'shook' — simpler vocabulary per craft notes"],
}


# ---------------------------------------------------------------------------
# Critique/revision phase — fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def critique_client():
    """Mock ClaudeClient for critique phase."""
    client = MagicMock()
    client.generate_structured.side_effect = [
        CRITIQUE_RESPONSE_1,
        CRITIQUE_RESPONSE_2,
        CRITIQUE_RESPONSE_3,
    ]
    return client


@pytest.fixture()
def state_with_prose(state_with_outline, prose_client):
    """State with scenes created by write_scene_prose."""
    write_scene_prose(state_with_outline, prose_client)
    return state_with_outline


# ---------------------------------------------------------------------------
# Critique/revision phase — tests
# ---------------------------------------------------------------------------


class TestCritiqueAndReviseUpdatesProse:
    """critique_and_revise() overwrites scene prose with revised version."""

    def test_prose_overwritten(self, state_with_prose, critique_client):
        """Each scene's prose is replaced with the revised version."""
        critique_and_revise(state_with_prose, critique_client)

        scenes = state_with_prose.metadata.scenes
        assert scenes[0].prose == CRITIQUE_RESPONSE_1["revised_prose"]
        assert scenes[1].prose == CRITIQUE_RESPONSE_2["revised_prose"]
        assert scenes[2].prose == CRITIQUE_RESPONSE_3["revised_prose"]


class TestCritiqueAndReviseCallsPerScene:
    """critique_and_revise() makes one Claude call per scene."""

    def test_one_call_per_scene(self, state_with_prose, critique_client):
        """Claude called once per scene."""
        critique_and_revise(state_with_prose, critique_client)

        assert critique_client.generate_structured.call_count == 3


class TestCritiqueAndReviseWritesChangelog:
    """critique_and_revise() writes change notes to critique/ directory."""

    def test_changelog_files_written(self, state_with_prose, critique_client):
        """critique/scene_01_changes.md exists with change descriptions."""
        critique_and_revise(state_with_prose, critique_client)

        critique_dir = state_with_prose.project_dir / "critique"
        assert (critique_dir / "scene_001_changes.md").exists()
        content = (critique_dir / "scene_001_changes.md").read_text()
        assert "Shortened the opening" in content


class TestCritiqueAndReviseCraftNotesInContext:
    """critique_and_revise() includes craft notes in Claude calls."""

    def test_craft_notes_in_user_message(self, state_with_prose, critique_client):
        """Craft notes are in the user message for consistency checking."""
        critique_and_revise(state_with_prose, critique_client)

        call_kwargs = critique_client.generate_structured.call_args_list[0].kwargs
        assert "sentence_structure" in call_kwargs["user_message"]


class TestCritiqueAndReviseMissingAnalysis:
    """critique_and_revise() raises when analysis.json is missing."""

    def test_missing_analysis_raises(self, tmp_path, critique_client):
        """No analysis.json raises FileNotFoundError."""
        state = ProjectState.create(
            project_id="no-analysis",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(1, "Test", "Some prose.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)

        with pytest.raises(FileNotFoundError, match="analysis.json"):
            critique_and_revise(state, critique_client)


class TestCritiqueAndReviseNoScenes:
    """critique_and_revise() raises when no scenes exist."""

    def test_no_scenes_raises(self, inspired_state, critique_client):
        """Empty scenes list raises ValueError."""
        # Write analysis.json so that's not the failure point
        (inspired_state.project_dir / "analysis.json").write_text(
            json.dumps(ANALYSIS_RESPONSE)
        )
        with pytest.raises(ValueError, match="No scenes"):
            critique_and_revise(inspired_state, critique_client)


class TestCritiqueAndReviseUpdatesMdFiles:
    """critique_and_revise() updates the scene .md files with revised prose."""

    def test_md_files_updated(self, state_with_prose, critique_client):
        """scenes/*.md files contain revised prose after critique."""
        critique_and_revise(state_with_prose, critique_client)

        scenes_dir = state_with_prose.project_dir / "scenes"
        content = (scenes_dir / "scene_001.md").read_text()
        assert CRITIQUE_RESPONSE_1["revised_prose"] in content


class TestCritiqueAndReviseResume:
    """critique_and_revise() skips already-critiqued scenes on resume."""

    def test_resume_skips_critiqued_scenes(self, state_with_prose, critique_client):
        """Scenes with existing changelog files are skipped on resume."""
        # Manually create changelog for scene 1 (simulating prior run)
        critique_dir = state_with_prose.project_dir / "critique"
        critique_dir.mkdir(exist_ok=True)
        (critique_dir / "scene_001_changes.md").write_text(
            "# Scene 1: The Arrival — Changes\n\n- Already revised\n"
        )

        # Only 2 calls needed (scenes 2 and 3)
        critique_client.generate_structured.side_effect = [
            CRITIQUE_RESPONSE_2,
            CRITIQUE_RESPONSE_3,
        ]

        critique_and_revise(state_with_prose, critique_client)

        # Scene 1 prose unchanged (not re-critiqued)
        assert state_with_prose.metadata.scenes[0].prose == PROSE_RESPONSE_1["prose"]
        # Scenes 2 and 3 revised
        assert state_with_prose.metadata.scenes[1].prose == CRITIQUE_RESPONSE_2["revised_prose"]
        assert critique_client.generate_structured.call_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_story_writer.py -k "Critique" -v`
Expected: FAIL — `critique_and_revise` raises `NotImplementedError`

**Step 3: Implement**

In `src/story_video/pipeline/story_writer.py`:

```python
CRITIQUE_SYSTEM = (
    "You are reviewing a scene for quality. Check for:\n"
    "- Consistency with craft notes (style drift)\n"
    "- Plot coherence with the story so far\n"
    "- Pacing issues\n"
    "- Flat or unnatural dialogue\n"
    "- Unclear prose\n\n"
    "Return the full revised text and a brief list of what you changed"
    " and why. If the scene needs no changes, return the original text"
    " with an empty changes list."
)

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "revised_prose": {
            "type": "string",
            "description": "The full revised scene text",
        },
        "changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of changes made and why",
        },
    },
    "required": ["revised_prose", "changes"],
}


def critique_and_revise(state: ProjectState, client: ClaudeClient) -> None:
    """Review and revise each scene's prose in a single pass.

    Reads analysis.json for craft notes and thematic brief. For each scene,
    sends prose + craft notes to Claude for critique. Overwrites scene.prose
    with revised version. Writes change notes to critique/ directory.

    Args:
        state: Project state with populated scenes.
        client: Claude API client.

    Raises:
        FileNotFoundError: If analysis.json is missing.
        ValueError: If no scenes exist.
    """
    analysis_path = state.project_dir / "analysis.json"
    if not analysis_path.exists():
        msg = f"analysis.json not found in {state.project_dir}"
        raise FileNotFoundError(msg)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    scenes = state.metadata.scenes
    if not scenes:
        msg = "No scenes in project"
        raise ValueError(msg)

    craft_notes_text = json.dumps(analysis["craft_notes"], indent=2)
    thematic_brief_text = json.dumps(analysis["thematic_brief"], indent=2)

    critique_dir = state.project_dir / "critique"
    critique_dir.mkdir(exist_ok=True)

    scenes_dir = state.project_dir / "scenes"

    for scene in scenes:
        # Resume support: skip scenes that already have a changelog file
        changes_filename = f"scene_{scene.scene_number:03d}_changes.md"
        if (critique_dir / changes_filename).exists():
            logger.info("Scene %d already critiqued — skipping", scene.scene_number)
            continue

        parts = [
            "## Craft Notes\n",
            craft_notes_text,
            "\n## Thematic Brief\n",
            thematic_brief_text,
            f"\n## Scene {scene.scene_number}: {scene.title}\n",
            scene.prose,
        ]
        user_message = "\n".join(parts)

        result = client.generate_structured(
            system=CRITIQUE_SYSTEM,
            user_message=user_message,
            tool_name="critique_scene",
            tool_schema=CRITIQUE_SCHEMA,
        )

        # Overwrite prose
        scene.prose = result["revised_prose"]

        # Write change notes
        changes_filename = f"scene_{scene.scene_number:03d}_changes.md"
        if result["changes"]:
            change_lines = [f"# Scene {scene.scene_number}: {scene.title} — Changes\n"]
            for change in result["changes"]:
                change_lines.append(f"- {change}")
            (critique_dir / changes_filename).write_text(
                "\n".join(change_lines) + "\n", encoding="utf-8"
            )
        else:
            (critique_dir / changes_filename).write_text(
                f"# Scene {scene.scene_number}: {scene.title} — No changes needed.\n",
                encoding="utf-8",
            )

        # Update .md file with revised prose
        md_filename = f"scene_{scene.scene_number:03d}.md"
        md_content = f"# Scene {scene.scene_number}: {scene.title}\n\n{scene.prose}\n"
        (scenes_dir / md_filename).write_text(md_content, encoding="utf-8")

    state.save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_story_writer.py -k "Critique" -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 6: Commit**

```bash
git add src/story_video/pipeline/story_writer.py tests/test_story_writer.py
git commit -m "feat: implement critique_and_revise phase for inspired_by mode"
```

---

### Task 8: Integration Test — Full Creative Flow

**Files:**
- Test: `tests/test_story_writer.py`

**Step 1: Write integration test**

This test exercises the full creative flow with mocked Claude calls, verifying data flows correctly from analysis through critique.

```python
class TestInspiredByIntegration:
    """Full inspired_by creative flow integration test."""

    def test_full_creative_flow(self, tmp_path):
        """All 5 creative phases run end-to-end with mocked Claude."""
        # --- Setup ---
        state = ProjectState.create(
            project_id="integration-test",
            mode=InputMode.INSPIRED_BY,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        source = tmp_path / "integration-test" / "source_story.txt"
        source.write_text("A short story about a cat who learns to fly.")

        client = MagicMock()

        # Configure mock responses for each phase
        client.generate_structured.side_effect = [
            # Phase 1: analyze_source
            ANALYSIS_RESPONSE,
            # Phase 2: create_story_bible
            BIBLE_RESPONSE,
            # Phase 3: create_outline (2 scenes for simplicity)
            {
                "scenes": [
                    {"scene_number": 1, "title": "The Discovery", "beat": "Cat finds wings.", "target_words": 200},
                    {"scene_number": 2, "title": "First Flight", "beat": "Cat takes off.", "target_words": 200},
                ],
                "total_target_words": 400,
            },
            # Phase 4: write_scene_prose (one per scene)
            {"prose": "The cat found wings in the attic.", "summary": "Cat finds mysterious wings."},
            {"prose": "She leaped from the windowsill and soared.", "summary": "Cat flies for the first time."},
            # Phase 5: critique_and_revise (one per scene)
            {"revised_prose": "The cat discovered wings in the dusty attic.", "changes": ["Added sensory detail"]},
            {"revised_prose": "She launched from the sill and caught the wind.", "changes": ["Stronger verb choice"]},
        ]

        # --- Execute all 5 phases ---
        analyze_source(state, client)
        create_story_bible(state, client)
        create_outline(state, client)
        write_scene_prose(state, client)
        critique_and_revise(state, client)

        # --- Verify end state ---
        # All artifact files exist
        project_dir = state.project_dir
        assert (project_dir / "analysis.json").exists()
        assert (project_dir / "story_bible.json").exists()
        assert (project_dir / "outline.json").exists()
        assert (project_dir / "scenes" / "scene_001.md").exists()
        assert (project_dir / "scenes" / "scene_002.md").exists()
        assert (project_dir / "critique" / "scene_001_changes.md").exists()

        # Scenes have revised prose (from critique, not original prose)
        scenes = state.metadata.scenes
        assert len(scenes) == 2
        assert "dusty attic" in scenes[0].prose
        assert "caught the wind" in scenes[1].prose

        # TEXT asset is COMPLETED for all scenes
        for scene in scenes:
            assert scene.asset_status.text == SceneStatus.COMPLETED

        # 7 total Claude calls: 1 analysis + 1 bible + 1 outline + 2 prose + 2 critique
        assert client.generate_structured.call_count == 7
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_story_writer.py::TestInspiredByIntegration -v`
Expected: PASS (all functions implemented in prior tasks)

**Step 3: Run full test suite**

Run: `pytest -m "not slow" -q`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/test_story_writer.py
git commit -m "test: add integration test for full inspired_by creative flow"
```

---

### Task 9: Update Documentation

**Files:**
- Modify: `BUGS_AND_TODOS.md`
- Modify: `DEVELOPMENT.md`
- Modify: `README.md`

**Step 1: Update BUGS_AND_TODOS.md**

Mark the inspired_by feature item as complete:
```
- [x] [feature] Implement inspired_by mode — analysis, bible, outline, prose, critique/revision (pipeline/story_writer.py, see docs/plans/2026-02-18-inspired-by-design.md)
```

**Step 2: Update DEVELOPMENT.md**

Add a new ADR for the inspired_by creative flow, documenting the file-based artifact storage decision.

**Step 3: Update README.md**

- Change "Up Next" to note that inspired_by is implemented, original is next
- Update "What's Working" list with creative flow bullet
- Update test count

**Step 4: Commit**

```bash
git add BUGS_AND_TODOS.md DEVELOPMENT.md README.md
git commit -m "docs: update tracking files for inspired_by mode completion"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | CLI `--premise` flag + unlock inspired_by | ~4 tests |
| 2 | Orchestrator dispatch + checkpoints | ~7 tests |
| 3 | `analyze_source()` | ~6 tests |
| 4 | `create_story_bible()` | ~5 tests |
| 5 | `create_outline()` | ~5 tests |
| 6 | `write_scene_prose()` | ~8 tests |
| 7 | `critique_and_revise()` | ~8 tests |
| 8 | Integration test | 1 test |
| 9 | Documentation updates | — |

**Total: ~44 new tests across 9 commits**

**Status:** Ready for execution
