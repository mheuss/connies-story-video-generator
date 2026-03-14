interface PhaseGuidance {
  title: string;
  description: string;
}

const PHASE_GUIDANCE: Record<string, PhaseGuidance> = {
  analysis: {
    title: "Source Analysis",
    description:
      "The AI analyzed your source text and identified the tone, themes, and characters. " +
      "Check that nothing important was missed or mischaracterized. " +
      "Edits here shape the entire story downstream.",
  },
  story_bible: {
    title: "Story Bible",
    description:
      "This defines your story's world — characters, settings, and narrative rules. " +
      "Make sure the details feel right before scenes are written.",
  },
  outline: {
    title: "Scene Outline",
    description:
      "A scene-by-scene plan for the story. Check the pacing and arc. " +
      "Adding or removing scenes here is much easier than after prose is written.",
  },
  scene_prose: {
    title: "Scene Prose",
    description:
      "The full written text for each scene. Read through for tone, dialogue, and flow. " +
      "This is what the narrator will speak.",
  },
  critique_revision: {
    title: "Critique & Revision",
    description:
      "The AI critiqued and revised each scene. Compare the revisions to the originals. " +
      "You can revert changes you disagree with by editing.",
  },
  scene_splitting: {
    title: "Scene Splitting",
    description:
      "Your source text has been split into individual scenes. " +
      "Check that the break points make sense and no text was lost.",
  },
  narration_flagging: {
    title: "Narration Flagging",
    description:
      "Words and phrases that might be tricky to pronounce have been flagged. " +
      "Review the flags — you can dismiss false positives.",
  },
  image_prompts: {
    title: "Image Prompts",
    description:
      "Visual descriptions that will be sent to the image generator. " +
      "Edit these to change what the AI draws — be specific about style, mood, and composition.",
  },
  narration_prep: {
    title: "Narration Prep",
    description:
      "How the narrator will pronounce names, numbers, and unusual words. " +
      "Fix anything that would sound wrong when spoken aloud.",
  },
  tts_generation: {
    title: "TTS Audio",
    description:
      "Listen to the generated narration for each scene. " +
      "If something sounds wrong, expand the text to check for issues. " +
      "You can edit the narration text and regenerate audio for individual scenes.",
  },
};

export function getPhaseGuidance(phase: string): PhaseGuidance | null {
  return PHASE_GUIDANCE[phase] ?? null;
}
