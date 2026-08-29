from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from radar.filters.keyword_filter import classify_item, classify_items_for_date, keyword_matches
from radar.models import Item, Source

# Fixtures publish on 2026-05-10; pinning classification one day later keeps
# novelty in the fresh-item band so threshold assertions stay deterministic
# regardless of when the suite runs (novelty is otherwise relative to now()).
FIXTURE_PUBLISHED_AT = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
FIXTURE_NOW = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)


def make_item(title: str, summary: str) -> Item:
    return Item(
        type="paper",
        title=title,
        normalized_title=title.casefold(),
        abstract_or_summary=summary,
        url="https://example.test/item",
        pdf_url=None,
        published_at=FIXTURE_PUBLISHED_AT,
        updated_at=None,
        source_name="arXiv cs.CV",
        external_id="x",
        arxiv_id="x",
        authors_json=[],
        organizations_json=[],
        metadata_json={},
    )


def test_classification_maps_calibration_geometry(app_config):
    item = make_item(
        "Camera Calibration for Multi-View 3D Reconstruction",
        "Bundle adjustment refines intrinsic calibration, lens distortion, and pose estimation "
        "for industrial cameras using a pinhole model.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Calibration & Camera Models" in result.tracks
    assert "3D Geometry & Reconstruction" in result.tracks
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_negative_topics_reduce_score_without_hard_delete(app_config):
    clean = make_item(
        "Camera Calibration for Industrial Inspection",
        "Camera calibration, camera model, lens distortion, bundle adjustment, "
        "and machine vision metrology.",
    )
    noisy = make_item(
        "Camera Calibration for Industrial Inspection and Face Recognition",
        "Camera calibration, camera model, lens distortion, bundle adjustment, machine vision "
        "metrology, and face recognition.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    clean_result = classify_item(clean, config=app_config, source=source)
    noisy_result = classify_item(noisy, config=app_config, source=source)
    assert noisy_result.negative_topic_penalty > 0
    assert noisy_result.final_score < clean_result.final_score
    assert "Calibration & Camera Models" in noisy_result.tracks


def test_keyword_matching_avoids_substring_false_positives():
    assert keyword_matches("sam", "SAM improves segmentation.")
    assert keyword_matches("multi-view", "multi view reconstruction")
    assert not keyword_matches("sam", "temporal-window sampling strategy")
    assert not keyword_matches("tracking", "benchmarking detectors")


def test_classify_items_for_date_persists_results(db_engine, app_config):
    with db_engine.begin() as connection:
        connection.execute(
            Item.__table__.insert(),
            [
                {
                    "type": "paper",
                    "title": "Camera Calibration with Bundle Adjustment",
                    "normalized_title": "camera calibration with bundle adjustment",
                    "abstract_or_summary": "Subpixel calibration target detection with radial "
                    "distortion correction and intrinsic calibration.",
                    "url": "https://example.test/a",
                    "pdf_url": None,
                    "published_at": datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
                    "updated_at": None,
                    "source_name": "arXiv cs.CV",
                    "external_id": "a",
                    "doi": None,
                    "arxiv_id": "a",
                    "authors_json": [],
                    "organizations_json": [],
                    "metadata_json": {},
                }
            ],
        )
    with db_engine.begin() as connection:
        assert connection.execute(select(Item)).first() is not None
    from radar.db import session_scope
    from radar.models import ItemClassification

    with session_scope(db_engine) as session:
        count = classify_items_for_date(
            session, app_config, datetime(2026, 5, 10).date(), now=FIXTURE_NOW
        )
        assert count == 1
        stored = session.scalar(select(ItemClassification))
        assert stored is not None
        assert stored.recommended_ring != "Ignore"


# Regression fixtures for the 2026-05-08 / 2026-05-11 noise patterns.
# Each test pins a concrete false-positive anchor so a future scoring change
# that re-introduces the issue would fail loudly.


def test_calibration_track_ignores_mllm_calibrated_accuracy(app_config):
    """Anchor: 2026-05-11 item 632 Omni-Persona.

    The paper introduces "Calibrated Accuracy" as an MLLM evaluation metric.
    The bare-word `calibration` keyword used to match it, putting an
    omnimodal-personalization paper on the Calibration & Camera Models track.
    """
    item = make_item(
        "Omni-Persona: Systematic Benchmarking and Improving Omnimodal Personalization",
        "We propose Calibrated Accuracy (Cal), which jointly rewards correct grounding "
        "and appropriate abstention. Strong recall can coexist with absent-persona "
        "hallucination, exposing calibration as a separate evaluation axis.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source)
    assert "Calibration & Camera Models" not in result.tracks
    # Negative topic (`omnimodal`) should also fire.
    assert "omnimodal" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_calibration_track_ignores_image_editing_distortion(app_config):
    """Anchor: 2026-05-08 item 97 EditRefiner.

    "Distortion localization" in an image-editing context used to false-positive
    the Calibration & Camera Models track via bare-word `distortion`.
    """
    item = make_item(
        "EditRefiner: A Human-Aligned Agentic Framework for Image Editing Refinement",
        "Recent text-guided image editing models still suffer from artifacts. "
        "EditRefiner outperforms state-of-the-art methods in distortion localization "
        "and human perception alignment for edited images.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source)
    assert "Calibration & Camera Models" not in result.tracks
    assert "image editing" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_mllm_benchmark_gets_negative_penalty(app_config):
    """Anchor: 2026-05-11 item 598 SciVQR.

    Generic MLLM evaluation benchmarks score 24–50 final and slip into the
    candidate queue with no industrial CV path. The `multimodal large language`
    negative topic should fire on the canonical phrasing.
    """
    item = make_item(
        "SciVQR: A Multidisciplinary Multimodal Benchmark for Advanced Scientific Reasoning",
        "Existing benchmarks for multimodal large language models (MLLMs) often fail to "
        "capture the complexity of reasoning processes. SciVQR covers 54 subfields in "
        "mathematics, physics, chemistry, geography, astronomy, and biology.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source)
    assert "multimodal large language" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_autonomous_driving_dataset_gets_negative_penalty(app_config):
    """Anchor: item 354 CARD ("A Multi-Modal Automotive Dataset for Dense 3D
    Reconstruction in Challenging Road Topography").

    The seed-script promoted CARD to Use because the classifier read it as a
    legitimate 3D-reconstruction / LiDAR / calibration paper. But the radar is
    industrial-CV focused — cars/lidars for autonomous driving are out of
    scope. The `autonomous driving` negative topic should fire on the abstract
    so future CARD-shape papers do not float into the candidate queue's top.
    `lidar` stays a positive keyword for industrial 3D sensing.
    """
    item = make_item(
        "CARD: A Multi-Modal Automotive Dataset for Dense 3D Reconstruction "
        "in Challenging Road Topography",
        "Autonomous driving must operate across diverse surfaces to enable safe "
        "mobility. CARD is a multi-modal driving dataset with synchronized "
        "global-shutter stereo cameras, LiDARs, and full calibration. It spans "
        "110 km across Germany and Italy and provides benchmarks for depth "
        "estimation and completion against KITTI baselines.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source)
    assert "autonomous driving" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_video_deflickering_gets_negative_penalty(app_config):
    """Anchor: 2026-05-20 item 1766 VDFP ("Video Deflickering with
    Flicker-banding Priors").

    VDFP is a screen-capture video-restoration paper, but it matched the
    Calibration & Camera Models + Sensors tracks and floated into the top-25
    candidate queue purely because flicker-banding is caused by rolling
    shutter. `rolling shutter` stays a legitimate positive keyword; the
    `deflickering` negative topic fires on the restoration task itself and
    drops the score so future VDFP-shape papers do not surface.
    """
    item = make_item(
        "VDFP: Video Deflickering with Flicker-banding Priors",
        "Capturing digital screens with smartphones frequently induces severe "
        "banding due to hardware synchronization mismatches. We propose VDFP, a "
        "perception-guided framework with a Degradation Field Modeling based on "
        "the rolling shutter mechanism, and release the DeViD dataset.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source)
    assert "deflickering" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_calibration_paper_survives_deflickering_negative_topic(app_config):
    """Guard: the `deflickering` negative topic must not touch a genuine
    rolling-shutter calibration paper — `rolling shutter` stays positive."""
    item = make_item(
        "Rolling-Shutter Camera Calibration for Industrial Metrology",
        "We estimate intrinsic calibration, lens distortion, and the rolling "
        "shutter readout model via bundle adjustment for industrial cameras "
        "using a pinhole model.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Calibration & Camera Models" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_industrial_inspection_dataset_still_matches_track(app_config):
    """Anchor: 2026-05-11 item 518 MMVIAD — a legitimate Watch/Evaluate item.

    MMVIAD mentions "video MLLMs" in its abstract but its primary signal is
    multi-view industrial anomaly detection. Make sure the noise-pattern fixes
    do not demote the legitimate Industrial Vision Inspection track match.

    2026-08-07: this test used to assert ``final_score >= thresholds.watch``.
    That assertion was passing only because `github` was a positive keyword,
    which inflated this benchmark's "Open-Source CV Tooling" score — a paper
    with a repository link is not a CV tool. Removing that keyword drops
    the fixture to 43.94, and the assertion was measuring the wrong thing
    twice over: the Watch threshold is not a real gate (attention is stubbed at
    0.0, so scores rarely reach 45), and queue membership is decided by rank,
    not by threshold. Checked against the real corpus instead: item 518 moves
    from rank 1/152 to rank 2/141 on 2026-05-11 — still comfortably in the
    top-25. What is pinned here is the intent: the track survives, no negative
    topic fires, and the score does not silently erode further.

    2026-08-11: the ratchet fired, which is what it is for. Removing the
    duplicate `open source` keyword (it compiled to the same regex as
    `open-source`, so this fixture's "commercial and open-source video MLLMs"
    was scoring the tooling track twice) drops the fixture from 43.94 to 40.64.
    The drop is the correction, not erosion — re-checked against the real
    corpus, item 518 sits at rank 4/140 on 2026-05-11, still far inside the
    top-25. Re-pinned at the new measured value.
    """
    item = make_item(
        "MMVIAD: Multi-view Multi-task Video Understanding for Industrial Anomaly Detection",
        "Industrial anomaly detection is critical for manufacturing quality control. "
        "MMVIAD contains object-centric 2-second inspection clips with approximately "
        "120 degrees of camera motion, covering 48 object categories and 6 structural "
        "anomaly types. Systematic evaluations on MMVIAD show that current commercial "
        "and open-source video MLLMs remain far below human performance. "
        "Source code is available at https://github.com/example/MMVIAD.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    # The repository URL no longer contributes a topic match; this fixture still
    # reaches Open-Source CV Tooling, but only via the words "open-source ...".
    assert "github" not in result.positive_keywords
    # Ratchet: pinned at the measured post-fix value so further erosion fails.
    assert result.final_score >= 40.6
    # Guard: the medical-imaging negative topics must not fire on a genuine
    # industrial-inspection paper ("inspection", "quality control" stay clean).
    assert result.negative_topic_penalty == 0


def test_image_restoration_papers_get_negative_penalty(app_config):
    """Anchor: 2026-05-22 candidate 11 (SANA-SR, item 2044).

    SANA-SR is a one-step diffusion super-resolution / image restoration model
    optimized for mobile deployment; it surfaced in the top-25 candidate queue
    only because the abstract matches `pruning`, `deployment`, and `benchmark`.
    The new `super-resolution` + `image restoration` negative topics close that
    gap without colliding with any positive radar keyword. Companion abstract
    fragments come straight from the SANA-SR abstract; we assert both negative
    topics fire and the recommended ring is Ignore.
    """
    item = make_item(
        "SANA-SR: Efficient One-Step Diffusion Restoration Model",
        "Real-world image super-resolution aims to recover high-quality images "
        "from complex degradations. We revisit Real-ISR from compact latent "
        "representation and linear-complexity modeling. SANA-SR achieves "
        "competitive image restoration on benchmark datasets; after pruning, "
        "the deployed model runs in 0.019s for practical mobile deployment.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert result.negative_topic_penalty > 0
    assert "super-resolution" in result.negative_keywords
    assert "image restoration" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_low_light_enhancement_papers_get_negative_penalty(app_config):
    """Anchor: 2026-05-22 candidate 13 (PixIE, item 2033).

    PixIE is a DINOv3-prompted low-light image enhancement (LLIE) framework —
    generic image-restoration work that surfaced only because the abstract
    matches `foundation model`, `dinov2`-class signals, and `reconstruction`.
    The `low-light image enhancement` negative topic fires on LLIE while
    leaving legitimate low-light sensor/calibration work untouched (those
    papers do not use the exact 4-word phrase).
    """
    item = make_item(
        "PixIE: Prompted Pixel-Space Low-Light Image Enhancement",
        "Low-light images exhibit severe noise, contrast loss, and semantic "
        "ambiguity. We propose PixIE, a feed-forward pixel-space low-light "
        "image enhancement framework prompted by a vision foundation model "
        "(DINOv3). Experiments on LLIE benchmarks show improved PSNR and "
        "reconstruction fidelity.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "low-light image enhancement" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_text_to_image_decoder_papers_get_negative_penalty(app_config):
    """Anchor: 2026-05-22 candidate 24 (PiD, item 1999).

    PiD is a pixel-diffusion decoder for high-resolution text-to-image latent
    decoding. It matched only `dinov2` and `reconstruction` (their VAE
    language). `text-to-image` closes the T2I-generation gap left open by the
    existing `image generation` / `image editing` negatives.
    """
    item = make_item(
        "PiD: Fast High-Resolution Latent Decoding with Pixel Diffusion",
        "Most practical high-resolution text-to-image systems perform "
        "generation in a compact latent space. We introduce PiD, a Pixel "
        "Diffusion decoder for high-resolution decoding, about 6x faster "
        "than cascaded diffusion-based super-resolution pipelines.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "text-to-image" in result.negative_keywords
    assert "super-resolution" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_calibration_paper_survives_image_restoration_negative_topics(app_config):
    """Guard: the new image-restoration / SR negative topics must not touch a
    genuine calibration / 3D reconstruction paper. The phrases we added
    (`super-resolution`, `image restoration`, `low-light image enhancement`,
    `text-to-image`) are specific enough that a calibration paper mentioning
    `reconstruction` and `lens distortion` stays clean."""
    item = make_item(
        "Bundle Adjustment for Multi-View 3D Reconstruction with Lens Distortion",
        "We refine intrinsic calibration, lens distortion, and the rolling "
        "shutter readout model via bundle adjustment for industrial cameras, "
        "improving 3D reconstruction accuracy.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Calibration & Camera Models" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_medical_imaging_papers_get_negative_penalty(app_config):
    """Anchor: 2026-05-21 curation queued 5 medical papers into 25 candidate
    slots. Medical imaging is outside the radar's industrial-CV scope; the
    medical-domain negative topics must penalize them and keep them in Ignore.
    Anchored on item 1956 (VEELA), a CT-angiography liver-vessel benchmark.

    `computed tomography` used to be the phrase that caught this item and was
    removed 2026-08-18 — it hit three kept industrial-XCT inspection papers at
    a keep rate dead on the base rate. `liver` and `clinically` replace it here
    and keep the anchor penalised without touching industrial CT.
    """
    item = make_item(
        "VEELA: A Clinically-Constrained Benchmark for Liver Vessel Segmentation "
        "in Computed Tomography Angiography",
        "Accurate segmentation of hepatic and portal vessels in contrast-enhanced "
        "computed tomography angiography remains challenging. We introduce a "
        "rigorously curated liver vessel dataset derived from 40 CTA scans, "
        "manually delineated under multi-expert clinical consensus, and a "
        "standardized benchmarking framework for vascular segmentation.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert result.negative_topic_penalty > 0
    assert "computed tomography" not in app_config.negative_topics.negative_topics
    assert "liver" in result.negative_keywords
    assert "clinically" in result.negative_keywords
    assert "clinical" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_video_qa_and_spatial_reasoning_papers_get_negative_penalty(app_config):
    """Anchor: 2026-08-06 candidates 8 / 23 / 25 (ChronoVision, GST-Bench, StreamArena).

    Six of that queue's 18 Ignore items were video-QA / spatial-reasoning /
    embodied-agent papers, and 14 of 18 carried no penalty at all. The
    `question answering`, `spatial reasoning`, `video reasoning` and
    `embodied agents` phrases close that gap. Each was probed against the whole
    decided corpus and hits zero kept items.
    """
    item = make_item(
        "GST-Bench: Can VLMs Develop Global Spatial Awareness from Video?",
        "Spatial intelligence is fundamental to embodied agents. We introduce a "
        "visual question answering benchmark for global spatial reasoning in video "
        "understanding, comprising human-verified questions derived from "
        "synthetically generated video, and evaluate 22 state-of-the-art VLMs.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "question answering" in result.negative_keywords
    assert "spatial reasoning" in result.negative_keywords
    assert "embodied agents" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_handwritten_matches_even_though_config_also_lists_handwriting(app_config):
    """Anchor: 2026-08-06 candidate 18 (DTRNet, item 8503), zero penalty.

    The matcher is whole-word, so a `handwriting` negative topic never fires on
    an abstract that says "handwritten". Both morphological forms are listed;
    this pins that the *written* form is the one real abstracts use.
    """
    item = make_item(
        "DTRNet: Dual Text-Radical Decoding for Handwritten Chinese Text Recognition",
        "In K-12 educational scenarios, handwritten Chinese text recognition should "
        "not only transcribe student writing but also detect faked characters. "
        "Code and the processed dataset are available at https://github.com/example/DTRNet.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "handwritten" in result.negative_keywords
    assert not keyword_matches("handwriting", item.abstract_or_summary.casefold())
    assert result.recommended_ring == "Ignore"


def test_github_url_alone_no_longer_creates_an_oss_tooling_track(app_config):
    """Pins the 2026-08-07 routing fix: `github` is not a topic keyword.

    Before the fix, any abstract carrying a repository URL matched the
    Open-Source CV Tooling track — 601 of that track's 807 matches over 1702
    curated items, at a keep rate (17%) indistinguishable from the 18.8% base
    rate. Code availability is already scored by `score_implementation`; the
    track keyword double-counted it into `relevance`. Real tooling words must
    still route.
    """
    fusion = make_item(
        "SafeDivertor: Faithful Divertor Heat Flux Reconstruction from Plasma Signals",
        "We introduce a signal-based reconstruction paradigm for time-resolved radial "
        "heat-flux profiles in magnetic-confinement fusion devices, with a benchmark "
        "dataset. The source code will be released on https://github.com/example/OpenFusion",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(fusion, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Open-Source CV Tooling" not in result.tracks
    assert "github" not in result.positive_keywords
    # The implementation signal still credits the repository link.
    assert result.implementation_score > 0

    real_tool = make_item(
        "An Open-Source Calibration Toolkit Built on OpenCV",
        "We release a computer vision toolkit and Python library for camera "
        "calibration, distributed as an SDK for industrial deployment.",
    )
    tool_result = classify_item(real_tool, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Open-Source CV Tooling" in tool_result.tracks


def test_multimodal_alone_no_longer_creates_a_foundation_model_track(app_config):
    """Pins the 2026-08-07 routing fix: `multimodal` is generic LLM vocabulary.

    It was the sole keyword carrying Vision Foundation Models 322 times at a 6%
    keep rate — 3x worse than the 18.8% base rate. The precise markers must
    still route the track.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    generic = make_item(
        "KVAE: Family of Tokenizers for Multimodal Generative Models",
        "This report presents a series of KVAE tokenizers for audio, image and video, "
        "all designed for subsequent text-conditioned multimodal generation.",
    )
    result = classify_item(generic, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Vision Foundation Models" not in result.tracks

    real_vfm = make_item(
        "Distilling DINOv2 Features for Efficient Dense Correspondence",
        "We distill a vision foundation model into a compact backbone and compare "
        "against CLIP and SAM baselines for industrial part matching.",
    )
    vfm_result = classify_item(real_vfm, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Vision Foundation Models" in vfm_result.tracks


def test_kept_items_survive_the_2026_08_07_routing_changes(app_config):
    """Guard for the routing fix: probed keepers must not be demoted.

    `video understanding`, `world model`, `embodied intelligence` and
    `temporal reasoning` were all rejected as negative topics precisely because
    they hit these kept items. MMVIAD is the standing industrial-inspection
    anchor; BWM is a kept robot-simulation item. Neither may pick up a penalty.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    mmviad = make_item(
        "MMVIAD: Multi-view Multi-task Video Understanding for Industrial Anomaly Detection",
        "Industrial anomaly detection is critical for manufacturing quality control. "
        "MMVIAD contains object-centric inspection clips covering 48 object categories "
        "and 6 structural anomaly types.",
    )
    mmviad_result = classify_item(mmviad, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in mmviad_result.tracks
    assert mmviad_result.negative_topic_penalty == 0

    simulator = make_item(
        "BWM: A Low-Cost High-Fidelity World Simulator for Robot Learning",
        "We present a world model simulator for embodied intelligence that renders "
        "RGB-D observations for robotics grasping and bin picking.",
    )
    sim_result = classify_item(simulator, config=app_config, source=source, now=FIXTURE_NOW)
    assert sim_result.negative_topic_penalty == 0


def test_open_source_keyword_is_not_listed_twice(app_config):
    """Pins the 2026-08-11 correctness fix: `open source` was a duplicate.

    ``keyword_matches`` splits a keyword on ``[\\s-]+`` and rejoins with
    ``[\\s-]+``, so `open source` and `open-source` compile to the *same*
    regex. Listing both scored the Open-Source CV Tooling track twice for every
    match - +36 instead of +18 on a title hit. The surviving single form must
    still match both spellings, so removing the duplicate costs no coverage.
    """
    tooling = next(t for t in app_config.topics.tracks if t.name == "Open-Source CV Tooling")
    assert tooling.positive_keywords.count("open-source") == 1
    assert "open source" not in tooling.positive_keywords
    # The one remaining form still matches the space spelling.
    assert keyword_matches("open-source", "we release our open source code")
    assert keyword_matches("open-source", "an open-source library")

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    item = make_item(
        "An Open Source Calibration Library",
        "We release an open-source library and toolkit for camera calibration.",
    )
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Open-Source CV Tooling" in result.tracks
    # Exactly one keyword recorded for the phrase, not two.
    assert result.positive_keywords.count("open-source") == 1


def test_edge_deployment_track_matches_without_the_word_deployment(app_config):
    """Anchor: items 7685 and 6162, both kept, both routed only via `deployment`.

    Probing `deployment` for removal exposed the coverage hole rather than
    justifying the removal: real edge papers say "sparsification", "embedded
    and mobile platforms" or name a board, and the track's precise vocabulary
    (`embedded vision`, `pruning`, `tensorrt`) missed all of it.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    lottery = make_item(
        "Lottery Tickets Are Not Production Tickets",
        "Reports on how sparsification, compression, and lottery tickets change model "
        "behavior have been mixed in the prior literature.",
    )
    result = classify_item(lottery, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Edge AI & Deployment" in result.tracks
    assert "sparsification" in result.positive_keywords
    assert "deployment" not in result.positive_keywords

    zipdepth = make_item(
        "ZipDepth: Lightweight Zero-Shot Monocular Depth on Any Device",
        "Their computational demands place them far beyond the reach of embedded and "
        "mobile platforms; our model runs at 30 fps on a Jetson board.",
    )
    zd = classify_item(zipdepth, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Edge AI & Deployment" in zd.tracks
    assert {"embedded", "fps", "jetson"} <= set(zd.positive_keywords)


def test_medical_modality_tail_gets_negative_penalty(app_config):
    """Anchor: 2026-08-08 item 8803 and 2026-08-07 item 8889, both zero-penalty.

    Medical stayed the #1 Ignore class across the 08-07..08-10 queues by
    leaking one modality at a time. Each phrase was probed against the whole
    decided corpus and hits zero kept items.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    ultrasound = make_item(
        "Bandit-Based Adaptive Prompting for Boundary-Sensitive Multi-Organ Segmentation",
        "Multi-organ ultrasound segmentation remains challenging when anatomically "
        "adjacent structures must be delineated jointly.",
    )
    result = classify_item(ultrasound, config=app_config, source=source, now=FIXTURE_NOW)
    assert "ultrasound" in result.negative_keywords
    assert "multi-organ" in result.negative_keywords
    assert result.recommended_ring == "Ignore"

    neuro = make_item(
        "International Transfer of Stochastic Cortical Self-Reconstruction",
        "Personalized mapping of gray matter atrophy, a hallmark of neurodegenerative "
        "disorders such as Alzheimer's disease, onto high-resolution cortical surfaces.",
    )
    neuro_result = classify_item(neuro, config=app_config, source=source, now=FIXTURE_NOW)
    assert "neurodegenerative" in neuro_result.negative_keywords


def test_bare_medical_is_not_a_negative_topic(app_config):
    """Guard for a phrase repeatedly considered and repeatedly rejected.

    Consolidating the medical tail to a bare `medical` was probed on
    2026-08-11: 74 hits but 6 of them kept, including item 3587 (Comparing
    Commercial Depth Sensor Accuracy for Medical Applications, Evaluate). The
    radar's own sensor-accuracy and anomaly-detection work mentions medical
    applications, so the bare word must stay out.
    """
    assert "medical" not in app_config.negative_topics.negative_topics
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    item = make_item(
        "Comparing Commercial Depth Sensor Accuracy for Medical Applications",
        "We evaluate structured light and time-of-flight depth cameras against a "
        "reference scanner for medical applications.",
    )
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "3D Sensors" in result.tracks
    assert result.negative_topic_penalty == 0


def test_vision_language_navigation_does_not_create_a_robotics_track(app_config):
    """Pins the 2026-08-11 track guard on Robotics Vision.

    `navigation` keeps a 12.1% keep rate when it is the sole keyword carrying
    the track, and vision-and-language navigation is the dominant wrong sense.
    Both phrasings hit zero kept items, so the guard needs no exemption.

    The guard is worth -12 against a track score of +18 for a title match and
    +10 for a body match, so it *removes* the track when VLN is mentioned only
    in the abstract and merely *demotes* it when the title says so too. Both
    behaviours are pinned here, because the partial case is the one that would
    otherwise be mistaken for the guard not working.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    body_only = make_item(
        "What Limits Instruction Following in Simulated Environments?",
        "Vision-language navigation asks an agent to follow natural language instructions "
        "and navigation cues indoors.",
    )
    result = classify_item(body_only, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Robotics Vision" not in result.tracks
    assert result.relevance_score == 0.0

    in_title = make_item(
        "What Limits Vision-and-Language Navigation?",
        "Vision-and-language navigation (VLN) asks an agent to follow natural language "
        "instructions through a simulated environment.",
    )
    title_result = classify_item(in_title, config=app_config, source=source, now=FIXTURE_NOW)
    # Track survives (18 - 12 = 6) but its relevance contribution is gutted.
    assert title_result.relevance_score == 6.0

    real = make_item(
        "Efficient Terrain Segmentation for Tiny Robot Navigation",
        "Terrain segmentation is a fundamental capability for autonomous navigation on "
        "microcontroller-class robotics hardware.",
    )
    real_result = classify_item(real, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Robotics Vision" in real_result.tracks
    assert real_result.relevance_score > title_result.relevance_score


def test_event_based_and_neuromorphic_reach_the_sensor_track(app_config):
    """Pins the 2026-08-12 3D Sensors coverage fix.

    `event camera` matches only that exact phrase, so papers that say
    "event-based" or "neuromorphic" instead were reaching queues on the
    format track (`benchmark` / `dataset`) rather than on sensor vocabulary.
    Both phrases keep at ~3x the base rate over the curated corpus.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    for title, summary in (
        (
            "M2E-UAV: A Benchmark for Onboard Motion-on-Motion Event-Based Tiny UAV Detection",
            "We release an event-based detection benchmark recorded from a moving platform.",
        ),
        (
            "Neuromorphic Object Detection: An In-Depth Study and Future Directions",
            "We study neuromorphic sensing pipelines for low-latency detection.",
        ),
    ):
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert "3D Sensors" in result.tracks, title

    # The pre-existing phrase must keep working on its own.
    only_long_form = make_item(
        "Calibration of an Event Camera Rig",
        "We calibrate an event camera against a global shutter reference.",
    )
    assert (
        "3D Sensors"
        in classify_item(only_long_form, config=app_config, source=source, now=FIXTURE_NOW).tracks
    )


def test_dynamic_range_is_not_a_sensor_keyword(app_config):
    """Guard for a phrase probed and rejected on 2026-08-12.

    `dynamic range` covers 18 items the Sensors track does not otherwise
    reach and keeps at 50%, but every one of them is an event-camera paper
    using "high dynamic range" as boilerplate. Adding it would score the same
    subject on two tracks and inflate relevance through the
    `strongest + 0.6 * rest` formula.
    """
    sensors = next(
        track for track in app_config.topics.tracks if track.name == "Sensors, Cameras & Standards"
    )
    assert "dynamic range" not in sensors.positive_keywords


def test_bare_defect_and_inspection_forms_route_industrial_work(app_config):
    """Pins the 2026-08-12 Industrial Vision Inspection coverage fix.

    Whole-word matching meant `defect detection` missed "defect segmentation"
    and "surface defects", and the two-word `* inspection` phrases missed
    "Semiconductor Inspection". `defect` keeps at 82.1% over the curated
    corpus — the highest-signal keyword measured anywhere in this config.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    for title, summary in (
        (
            "XCT-SAM: Domain Adaptation of SAM for Industrial XCT Defect Segmentation",
            "We adapt a segmentation backbone to X-ray computed tomography scans of castings.",
        ),
        (
            "Does Super-Resolution Preserve Defect Evidence?",
            "A low-false-call benchmark for semiconductor inspection.",
        ),
        (
            "A Multimodal Anomaly Benchmark for Li-Ion Battery Electrode Manufacturing",
            "Electrode coating lines produce surface defects that must be graded in line.",
        ),
    ):
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert "Industrial Vision Inspection" in result.tracks, title


def test_industrial_inspection_long_forms_are_kept_alongside_bare_ones(app_config):
    """The 2026-08-12 addition is additive, not a consolidation.

    Dropping the long forms in favour of the bare ones they subsume was A/B'd
    and rejected: it demoted item 2042 (Industrial Inspection DINOv3,
    Evaluate) from rank 3 to 10. The long forms are strictly more on-domain,
    and the extra weight encodes that — unlike the `open source` /
    `open-source` duplicate, which compiled to one regex and added nothing.
    """
    track = next(t for t in app_config.topics.tracks if t.name == "Industrial Vision Inspection")
    for keyword in ("industrial inspection", "visual inspection", "defect detection"):
        assert keyword in track.positive_keywords

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    specific = classify_item(
        make_item(
            "Rethinking Transfer Learning for Industrial Inspection",
            "We compare DINOv3 and ImageNet pretraining for industrial inspection of "
            "RGB and X-ray defect images.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    generic = classify_item(
        make_item(
            "An Inspection Pipeline for Bridges",
            "We inspect concrete surfaces from drone imagery.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert specific.relevance_score > generic.relevance_score


def test_benchmark_stays_a_datasets_track_keyword(app_config):
    """Guard for the config's largest and most-often-reconsidered lever.

    Removing `benchmark` is the biggest measurable noise win available (174
    decided-Ignore items pushed out over 49 dates) and has now been rejected
    three times, most recently on 2026-08-12. The reason is that the kept
    items it demotes are this radar's own industrial-inspection benchmark
    papers — an on-domain paper that publishes a benchmark is exactly what
    should rank highly, and `benchmark` is what lifts it.
    """
    track = next(t for t in app_config.topics.tracks if t.name == "Datasets & Benchmarks")
    assert "benchmark" in track.positive_keywords

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "LIBAD: A Multimodal Anomaly Detection Benchmark for Battery Electrode Lines",
            "We publish a benchmark and dataset for in-line electrode defect grading.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Datasets & Benchmarks" in result.tracks
    assert "Industrial Vision Inspection" in result.tracks


def test_scoped_driving_negatives_do_not_penalise_geometry_work(app_config):
    """Pins the scoped form of the 2026-08-12 driving negatives.

    Bare `driving` was probed and rejected: 97 hits but 11 of them kept,
    including LiDAR-camera extrinsic calibration and global SfM work. The
    scoped `driving scene` / `surround-view` forms hit zero kept items.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "driving" not in negatives
    assert "driving scene" in negatives
    assert "surround-view" in negatives

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    kept = make_item(
        "Geometry-Preserving 3D Gaussian Splatting for LiDAR-Camera Extrinsic Calibration",
        "We calibrate a LiDAR against a camera while driving a survey vehicle.",
    )
    kept_result = classify_item(kept, config=app_config, source=source, now=FIXTURE_NOW)
    assert kept_result.negative_topic_penalty == 0

    noise = make_item(
        "Feed-Forward Gaussians for Surround-View Driving Reconstruction",
        "We reconstruct driving scenes from sparse surround-view rigs.",
    )
    noise_result = classify_item(noise, config=app_config, source=source, now=FIXTURE_NOW)
    assert noise_result.negative_topic_penalty > 0


def test_relative_pose_vocabulary_routes_the_five_point_paper(app_config):
    """Pins the 2026-08-14 geometry additions.

    Item 9266 (Fast Iterative Five point Relative Pose Estimation, Prototype)
    ranked 14 in its queue because 3D Geometry & Reconstruction had no word for
    relative-pose or robust-estimation geometry, and `structure from motion`
    misses the abstract's "Structure and Motion". With the additions it goes to
    rank 1. The keywords are re-ranking vocabulary, not coverage: they add
    almost no new items, they stop on-domain geometry papers from tying with
    format-track noise.
    """
    keywords = next(
        track.positive_keywords
        for track in app_config.topics.tracks
        if track.name == "3D Geometry & Reconstruction"
    )
    for keyword in ("relative pose", "ransac", "robust estimation", "structure and motion"):
        assert keyword in keywords

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    five_point = make_item(
        "Fast Iterative Five point Relative Pose Estimation",
        "Robust estimation of the relative pose between two cameras is a fundamental part "
        "of Structure and Motion methods. For calibrated cameras, the five point method "
        "together with a robust estimator such as RANSAC gives the best result.",
    )
    result = classify_item(five_point, config=app_config, source=source, now=FIXTURE_NOW)
    assert "3D Geometry & Reconstruction" in result.tracks
    for keyword in ("relative pose", "ransac", "robust estimation", "structure and motion"):
        assert keyword in result.positive_keywords
    assert result.negative_topic_penalty == 0

    # Same paper without the new vocabulary would have matched `pose estimation`
    # alone; the additions must be worth strictly more than that.
    thin = make_item(
        "Fast Iterative Five point Estimation",
        "We revisit a classical problem and report ground truth comparisons.",
    )
    thin_result = classify_item(thin, config=app_config, source=source, now=FIXTURE_NOW)
    assert result.relevance_score > thin_result.relevance_score


def test_both_hyphenated_and_bare_6dof_forms_are_listed(app_config):
    """`keyword_matches` splits on `[\\s-]+`, so `6-dof` cannot match "6dof".

    Same mechanical trap as `handwritten` / `handwriting`: whichever spelling
    an abstract happens to use has to be listed literally.
    """
    keywords = next(
        track.positive_keywords
        for track in app_config.topics.tracks
        if track.name == "3D Geometry & Reconstruction"
    )
    assert "6-dof" in keywords
    assert "6dof" in keywords
    assert keyword_matches("6-dof", "6-DoF pose") is True
    assert keyword_matches("6-dof", "6DoF pose") is False
    assert keyword_matches("6dof", "6DoF pose") is True


def test_video_clip_guards_the_foundation_model_track(app_config):
    """Pins the 2026-08-14 CLIP false-context guard.

    Whole-word matching cannot tell the CLIP model from a video clip, and
    long-video papers use the segment sense constantly. Neither `video clip`
    nor `video clips` appears in any kept item, so the guard is free. Both
    forms are listed because `video clip` compiles to `video[\\s-]+clip`, which
    does not match "clips".
    """
    guards = next(
        track.negative_keywords
        for track in app_config.topics.tracks
        if track.name == "Vision Foundation Models"
    )
    assert "video clip" in guards
    assert "video clips" in guards

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    wrong_sense = make_item(
        "Streaming Audio Description Generation for Long-form Videos",
        "Most existing methods frame the task as video clip captioning, requiring "
        "ground-truth timestamps for each clip.",
    )
    result = classify_item(wrong_sense, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Vision Foundation Models" not in result.tracks

    real = make_item(
        "Zero-Shot Anomaly Detection with CLIP Text Anchors",
        "We anchor normal and abnormal semantics with CLIP for industrial anomaly detection.",
    )
    real_result = classify_item(real, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Vision Foundation Models" in real_result.tracks


def test_2026_08_14_negative_tail_penalises_its_classes(app_config):
    """Pins the 2026-08-14 negative batch, one item per class it was mined from.

    Every phrase hits zero kept items over 1986 curated items. The rejected
    broad forms are pinned in the companion test below.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = {
        "forgery": make_item(
            "Learning Unified Video and Image Representation for Video Face Forgery Detection",
            "Face forgery detection is crucial given rapid developments in deep generative models.",
        ),
        "narrative": make_item(
            "A Benchmark for Narrative Evolution in Extreme Long Video",
            "Long-form video understanding includes tracking an evolving narrative.",
        ),
        "image compression": make_item(
            "Hessian-Aware Mixed-Precision Post-Training Quantization",
            "Learned image compression models achieve strong rate-distortion performance.",
        ),
        "whole-body": make_item(
            "Towards a Human-Aligned Motion Tracking Benchmark",
            "Humanoid motion tracking is central to teleoperation and whole-body imitation.",
        ),
        "business": make_item(
            "A Multimodal Benchmark and Agents for Real-World Business Ideation",
            "Agentic systems have opened new opportunities for business ideation.",
        ),
    }
    for phrase, item in cases.items():
        result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
        assert phrase in result.negative_keywords, phrase
        assert result.negative_topic_penalty > 0, phrase


def test_broad_forms_rejected_on_2026_08_14_stay_out(app_config):
    """Each of these was probed and hit kept items; pin them so they stay out.

    `image fusion` hits 8840 (irpol-fuse), `egocentric` hits 8 kept items,
    `hand pose` hits 826 and 803, `humanoid` hits 3, `cultural` hits 8004 and
    9245, `explainable` hits 8762 (RobustDefect-LLM, an industrial surface
    defect paper), `species` hits 7749. The scoped forms actually added are
    asserted alongside so the pair stays legible.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in (
        "image fusion",
        "egocentric",
        "hand pose",
        "humanoid",
        "cultural",
        "explainable",
        "species",
        "avatar",
        "motion tracking",
    ):
        assert rejected not in negatives, rejected
    for scoped in (
        "visible image fusion",
        "prosthetic",
        "whole-body",
        "explainable artificial intelligence",
        "plant species",
        "head avatar",
    ):
        assert scoped in negatives, scoped

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    kept = make_item(
        "RobustDefect-LLM: Explainable and Robustness-Aware Industrial Defect Classification",
        "We classify industrial surface defects with explainable predictions under domain shift.",
    )
    result = classify_item(kept, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert result.negative_topic_penalty == 0


def test_medical_tail_2026_08_18_penalises_the_phrases_that_missed_9348(app_config):
    """Item 9348 took rank 1 of the 08-17 queue with zero penalty.

    Its abstract says "medical AI", "radiological" and "breast MRI"; the filter
    carried `radiology` and `medical imaging` and matched neither, because the
    matcher is whole-word. Pin the real title so the miss cannot come back.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    item = make_item(
        "Unsupervised Anomaly Detection for Image Dataset Quality Assurance "
        "in Multi-Center Breast MRI",
        "Corrupted data silently threatens the safety of medical AI. We propose a taxonomy of "
        "radiological image anomalies and build a controlled benchmark from six public datasets.",
    )
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "mri" in result.negative_keywords
    assert "radiological" in result.negative_keywords
    assert result.negative_topic_penalty > 0

    cases = {
        "patient": make_item(
            "Cross-Modality Translation for Longitudinal Follow-Up",
            "We synthesize follow-up scans for each patient in a multi-center cohort.",
        ),
        "medical image": make_item(
            "Cold Start Active Adaptation of SAM",
            "Annotation budgets limit medical image segmentation models.",
        ),
        "anatomy": make_item(
            "Physics-Guided Attenuation Correction",
            "Anatomical priors are unreliable, so we supervise on anatomy directly.",
        ),
        "cancer": make_item(
            "Benchmarking Deep Architectures for Histology",
            "Lung cancer remains the leading cause of mortality worldwide.",
        ),
        "pathology": make_item(
            "A Unified Slide-Level Encoder",
            "Computational pathology benefits from slide-level pretraining.",
        ),
        "physiological": make_item(
            "Contactless Sensing from Thermal Video",
            "Removing wearables removes the physiological supervision signal.",
        ),
        "echocardiography": make_item(
            "A Unified Framework for LVEF Estimation",
            "Echocardiography provides complementary cardio-oncology information.",
        ),
        "presentation attack": make_item(
            "Towards Zero-Shot Domain Generalization for ID Cards",
            "Presentation attack detection for national ID cards lacks genuine samples.",
        ),
    }
    for phrase, case in cases.items():
        result = classify_item(case, config=app_config, source=source, now=FIXTURE_NOW)
        assert phrase in result.negative_keywords, phrase
        assert result.negative_topic_penalty > 0, phrase


def test_medical_phrases_rejected_on_2026_08_18_stay_out(app_config):
    """These hit kept items when probed; keeping them out is the whole point.

    `x-ray` is the sharpest case: its kept hits are X-ray tomography of
    aerospace defects, XCT-SAM industrial domain adaptation and hazelnut X-ray
    grading — the radar's own non-destructive inspection work. Bare `breast`
    is excluded for the same reason (woody-breast poultry fillet grading).
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in (
        "x-ray",
        "diagnostic",
        "surgery",
        "microscopy",
        "retinal",
        "anatomical",
        "endoscopic",
        "biomedical",
        "disease",
        "breast",
        "medical",
    ):
        assert rejected not in negatives, rejected
    for scoped in ("mri", "medical image", "radiological", "patient", "cancer"):
        assert scoped in negatives, scoped

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    kept = make_item(
        "Interpretable Computer Vision for Defect Detection in X-ray Tomography "
        "of Aerospace Composites",
        "We inspect aerospace parts with X-ray computed tomography and localize manufacturing "
        "defects without a labelled defect set.",
    )
    result = classify_item(kept, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert result.negative_topic_penalty == 0


def test_inspection_and_metrology_coverage_added_2026_08_18(app_config):
    """`crack`, `damage detection` and `control points` were the coverage holes.

    Item 9453 (YOLO26-RD, Evaluate) ranked 22 on `dataset` alone and 9634
    (Beyond Control Points, Evaluate) ranked 17 on `absolute pose` alone. The
    A/B moved them to rank 3 and 6 with no kept item lost on score.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)

    yolo_rd = make_item(
        "YOLO26-RD: An End-to-End Road Damage Detection Network With Learnable "
        "Contrast Enhancement and Edge-Guided Downsampling",
        "Automated pavement-distress detection is commonly framed as a small-object problem. "
        "We present a differentiable analogue of CLAHE that adapts contrast per tile.",
    )
    result = classify_item(yolo_rd, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert "damage detection" in result.positive_keywords

    crack = make_item(
        "Multi-Task Crack Foundation Model for Engineering-Reliable Crack Representation",
        "We learn a shared representation for crack segmentation across infrastructure surfaces.",
    )
    result = classify_item(crack, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert "crack" in result.positive_keywords

    control = make_item(
        "Beyond Control Points: Arcsecond Relative-Motion Estimation of Vision "
        "Measurement Platforms With Incomplete or Absent Control Fields",
        "Long-range vision-based deformation monitoring is sensitive to platform motion. "
        "We estimate inter-frame motion from image displacements and known 3D points.",
    )
    result = classify_item(control, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Calibration & Camera Models" in result.tracks
    assert "control points" in result.positive_keywords


def test_photogrammetric_is_the_whole_word_sibling_of_photogrammetry(app_config):
    """`\\bphotogrammetry\\b` never fires on "photogrammetric" — same miss as
    radiology / radiological, and the same fix: list both forms."""
    assert not keyword_matches("photogrammetry", "a photogrammetric network adjustment")
    assert keyword_matches("photogrammetric", "a photogrammetric network adjustment")

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    item = make_item(
        "Robust Photogrammetric Network Design for Aerial-Ground Imagery",
        "We refine a photogrammetric adjustment with detector-free matching.",
    )
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "3D Geometry & Reconstruction" in result.tracks
    assert "photogrammetric" in result.positive_keywords


def test_pnp_keyword_is_kept_despite_the_plug_and_play_collision(app_config):
    """Item 9405 matched `pnp` on "PnP-3D layer", i.e. plug-and-play.

    `pnp` is nonetheless 73% kept over 11 hits (6D pose, PnP on a neuromorphic
    processor, visual localization), and the obvious guard `plug-and-play` hits
    4 kept items including 9508 (VGGT-Align, Prototype) and 9039. So the
    collision is accepted and neither side is changed — pinned so a later round
    does not re-litigate it.
    """
    tracks = {track.name: track for track in app_config.topics.tracks}
    geometry = tracks["3D Geometry & Reconstruction"]
    assert "pnp" in geometry.positive_keywords
    assert "plug-and-play" not in geometry.negative_keywords
    assert "plug-and-play" not in app_config.negative_topics.negative_topics


def test_agentic_and_motion_negatives_added_2026_08_18_round2(app_config):
    """The 08-16 queue put two zero-penalty embodied-agent papers in its top four.

    9439 (appliance manipulation) took rank 2 and 9435 (visual dexterity in
    simulation) rank 4, both carrying nothing but the format tracks. `benchmark`
    is settled as un-removable, so the fix is to name each class's subject.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)

    appliance = make_item(
        "Scaling Manual-Grounded Appliance Manipulation with Data Synthesis and Unified Planning",
        "Operating a household appliance requires long-horizon planning that is stateful. "
        "We synthesize demonstrations and train a unified planner.",
    )
    result = classify_item(appliance, config=app_config, source=source, now=FIXTURE_NOW)
    assert "appliance" in result.negative_keywords
    assert result.negative_topic_penalty > 0

    gui_agent = make_item(
        "UI-Mate: Advancing Open-Weight Foundation GUI Agents with In-Context Demonstrations",
        "Foundation GUI agents still trail proprietary systems on computer-use benchmarks.",
    )
    result = classify_item(gui_agent, config=app_config, source=source, now=FIXTURE_NOW)
    assert "gui" in result.negative_keywords
    assert "computer-use" in result.negative_keywords
    assert result.negative_topic_penalty > 0

    cases = {
        "chain-of-thought": make_item(
            "Look Light, Think Heavy: What Multimodal Reasoning Can and Cannot Do",
            "We evaluate zero-shot and chain-of-thought prompting across four model families.",
        ),
        "reward model": make_item(
            "Standardized Evaluation for Cross-Platform Agents",
            "A reward model scores each trajectory step without human annotation.",
        ),
        "human motion": make_item(
            "Sen-Cap: Sensor-Flexible and Noise-Resilient Capture via LiDAR-Camera Integration",
            "LiDAR-based 3D human motion capture has broad application value.",
        ),
        "action recognition": make_item(
            "Bitstream Action Recognition is Byte Modeling",
            "Conventional action recognition decodes video before it classifies anything.",
        ),
        "motion generation": make_item(
            "Self-Intersection-Aware Generation Using an Efficient Sphere Proxy",
            "Text-conditioned motion generation has progressed rapidly.",
        ),
        "audio-visual": make_item(
            "OmniVideo-100K: A Dataset for Reasoning through Structured Scripts",
            "Real-world audio-visual understanding requires multi-hop trajectory reasoning.",
        ),
        "emotion": make_item(
            "A Balanced Speaker-Segment Multimodal Benchmark",
            "Understanding human emotion in spoken conversation remains unsolved.",
        ),
        "heart rate": make_item(
            "CardiacMamba: Fair and Robust RGB-RF Fusion via State Space Modeling",
            "Remote photoplethysmography estimates heart rate without contact.",
        ),
        "e-commerce": make_item(
            "PosterText: Towards Unified Visual Text Generation and Editing",
            "Automated e-commerce poster design requires high fidelity and layout control.",
        ),
        "video editing": make_item(
            "GRNEdit: Efficient General Video Editing from a Binary-Evidence Perspective",
            "Recent video editing models rely on heavy diffusion backbones.",
        ),
        "land cover": make_item(
            "A Controlled Benchmark of Lightweight CNNs on DeepGlobe",
            "High-resolution satellite imagery drives land-cover segmentation.",
        ),
        "phenotyping": make_item(
            "Population Structure Analysis of an Inbred Population",
            "Quantitative shape phenotyping from stereo retinal photographs.",
        ),
        "iris recognition": make_item(
            "Cross-Sensor Generalization for Ocular Biometrics",
            "Iris recognition degrades when the acquisition sensor changes.",
        ),
    }
    for phrase, case in cases.items():
        result = classify_item(case, config=app_config, source=source, now=FIXTURE_NOW)
        assert phrase in result.negative_keywords, phrase
        assert result.negative_topic_penalty > 0, phrase


def test_round2_2026_08_18_broad_forms_stay_out(app_config):
    """Every phrase here hit a kept item when probed against the whole corpus.

    `satellite` is the headline rejection: the whole family (`satellite`,
    `satellite imagery`, `satellite image`, `geo-localization`) hits 6669
    (NGPS aerial geo-localization), so `land cover` is taken instead.
    `fashion` and `household` are the figurative/incidental rejections — both
    are 0-kept today but 4 of 16 `fashion` hits are "in an end-to-end fashion"
    and 2 of 9 `household` hits are YCB-style object-pose datasets.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in (
        "satellite",
        "satellite imagery",
        "satellite image",
        "geo-localization",
        "aerial imagery",
        "long-horizon",
        "knowledge distillation",
        "visual grounding",
        "dexterous",
        "dexterous manipulation",
        "human pose",
        "hallucination",
        "scene generation",
        "motion capture",
        "pedestrian",
        "gaze",
        "instruction following",
        "federated learning",
        "text-to-video",
        "fashion",
        "household",
        "poster",
    ):
        assert rejected not in negatives, rejected
    for scoped in ("land cover", "appliance", "gaze estimation", "3d scene generation"):
        assert scoped in negatives, scoped

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    kept = make_item(
        "FedTR: Federated Learning Framework with Transfer Learning for Industrial "
        "Visual Inspection",
        "Factories cannot share defect images, so we train an inspection model with federated "
        "learning and knowledge distillation across plants.",
    )
    result = classify_item(kept, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert result.negative_topic_penalty == 0


def test_multi_view_clustering_guards_the_geometry_track(app_config):
    """`multi-view` is a real geometry keyword; multi-view clustering is not.

    9449 reached rank 8 of the 08-16 queue on `multi-view` alone with no other
    keyword and no penalty. The guard is track-local because the wrong sense is
    track-local — a -12 track hit is worth more than the -25 global penalty
    once the 0.55 relevance weight is applied. It demotes rather than removes:
    a title hit is +18, so the track survives at +6 and the item simply stops
    tying with real geometry work.
    """
    tracks = {track.name: track for track in app_config.topics.tracks}
    assert "multi-view clustering" in tracks["3D Geometry & Reconstruction"].negative_keywords
    assert "multi-view clustering" not in app_config.negative_topics.negative_topics

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = make_item(
        "Beyond Independence: Learning Correlated Views for Variational Incomplete "
        "Multi-View Clustering",
        "Incomplete multi-view clustering assumes view independence, which discards the "
        "correlation between views.",
    )
    control = make_item(
        "Beyond Independence: Learning Correlated Views for Variational Incomplete "
        "Multi-View Fusion",
        "Incomplete multi-view fusion assumes view independence, which discards the "
        "correlation between views.",
    )
    noisy = classify_item(noise, config=app_config, source=source, now=FIXTURE_NOW)
    clean = classify_item(control, config=app_config, source=source, now=FIXTURE_NOW)
    assert noisy.relevance_score == clean.relevance_score - 12
    assert noisy.final_score < clean.final_score
    assert noisy.negative_topic_penalty == 0

    geometry = make_item(
        "Multi-View Stereo with Learned Correspondence Priors",
        "We fuse multi-view depth maps and refine the surface reconstruction with bundle "
        "adjustment over the estimated camera poses.",
    )
    result = classify_item(geometry, config=app_config, source=source, now=FIXTURE_NOW)
    assert "3D Geometry & Reconstruction" in result.tracks
    assert "multi-view" in result.positive_keywords
    assert result.relevance_score > noisy.relevance_score


def test_domain_noise_tail_2026_08_19_penalises_its_classes(app_config):
    """Hand-mined from the 157 zero-penalty Ignore items published since 08-01.

    Every phrase was probed against the full decided corpus and has zero kept
    hits. Counts are `hits/incremental` over 2006 decided items, where
    incremental counts only items no existing negative already reaches:
    marine 6/5, salient object 6/4, document retrieval 3/3, astronomy 3/2,
    document understanding 6/2, astronomical 1/1, speech 9/1.
    """
    negatives = app_config.negative_topics.negative_topics
    for phrase in (
        "marine",
        "salient object",
        "speech",
        "document understanding",
        "document retrieval",
        "astronomy",
        "astronomical",
    ):
        assert phrase in negatives, phrase

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "S3AM: A Single-Stream SAM with Reliability-Calibrated Frequency Adapter for "
            "Multi-modal Salient Object Detection",
            "Vision foundation models have advanced multi-modal salient object detection "
            "through parameter-efficient tuning on RGB-D benchmarks.",
        ),
        (
            "Leveraging existing sparse point annotations for benthic imagery dense segmentation",
            "The health of marine ecosystems is a critical indicator of global "
            "environmental change, yet underwater observation limits systematic monitoring.",
        ),
        (
            "A General-Purpose VLM Can Teach an Astronomy Foundation Model to Better "
            "Recognize Galaxy Morphology",
            "We distil an astronomical survey classifier from a general-purpose model and "
            "evaluate it on a galaxy morphology benchmark.",
        ),
        (
            "DistilVDR: A Compact End-to-End Visual Document Retriever",
            "Visual document retrieval and document understanding pipelines rely on large "
            "encoders; we distil them into a compact student.",
        ),
        (
            "VSRo-200: A Romanian Visual Speech Recognition Dataset",
            "We release a dataset for visual speech recognition and study the effect of "
            "supervision on the resulting benchmark.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert result.negative_topic_penalty > 0, title


def test_2026_08_19_broad_forms_stay_out(app_config):
    """Broad siblings of this round's phrases were probed and rejected.

    `saliency` (26 hits, 5 kept) is the broad-form trap from
    [[broad-form-negative-trap]]: saliency maps are a legitimate
    interpretability tool in kept work, so only the narrow `salient object`
    is taken. `underwater` (11, 1 — 6161 Wat3R underwater 3D geometry),
    `species` (21, 1), `ecological` (8, 1) and `ecosystem` (6, 1) all touch a
    kept item. `sound` has a clean kept count over 5 hits but is rejected on
    the figurative-usage grep — "confirming the representation is sound" is the
    standard CV-abstract idiom.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in (
        "saliency",
        "underwater",
        "species",
        "ecological",
        "ecosystem",
        "sound",
        "movie",
        "skeleton-based",
        "world model",
        "video understanding",
        "egocentric",
        "novel view synthesis",
        "surveillance",
        "sports",
    ):
        assert rejected not in negatives, rejected

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    kept = make_item(
        "Wat3R: Underwater 3D Geometry Learning without Annotations",
        "Estimating underwater scene geometry is hard because refraction breaks the pinhole "
        "model; we recover camera pose and depth estimation from raw stereo footage.",
    )
    result = classify_item(kept, config=app_config, source=source, now=FIXTURE_NOW)
    assert "3D Geometry & Reconstruction" in result.tracks
    assert result.negative_topic_penalty == 0


def test_marine_collides_with_geotechnical_soil_descriptions(app_config):
    """`marine` is the one phrase in the 08-19 round with an on-domain collision.

    8634 (TriView-YOLO, ground-penetrating-radar cavity detection) says "soft
    marine clay" as a soil descriptor. GPR cavity detection is NDT adjacency the
    radar cares about, so this pins the cost: the item takes the penalty but
    keeps its inspection routing, and the demotion is bounded to one negative
    topic. If a marine-inspection item is ever kept, swap `marine` for the
    narrow forms (`marine species`, `marine ecology`, `marine survey`).
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    item = make_item(
        "TriView-YOLO: Early Multi-View Fusion for Ground Penetrating Radar Cavity Detection",
        "We detect subsurface cavities for non-destructive infrastructure inspection. The test "
        "set comes exclusively from the Bangkok surveys, over soft marine clay with a high "
        "water table.",
    )
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert result.negative_topic_penalty > 0


def test_2026_08_24_ai_media_forensics_is_penalised(app_config):
    """AI-media forensics was the 08-19..08-21 window's #1 zero-penalty class.

    `deepfake` has been listed since May but covers only the video half; the
    still-image forensics half — forgery localization, manipulation
    localization, AI-generated-image detection — was entirely unpenalised.
    Each phrase hits zero of the 490 kept items in the 2190-item decided
    corpus.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "GAP-SAM: A Global Artifact Prior for Generalizable AI-Generated Image "
            "Manipulation Localization",
            "AI-generated image manipulation localization identifies edited pixels, but "
            "pixel supervision entangles forensic evidence with dataset-specific mask "
            "geometry.",
        ),
        (
            "Frozen DINO Localizes Image Edits Without a Localizer",
            "Localized image edits can change a photograph's meaning, so forensic analysis "
            "must identify where an edit occurred.",
        ),
        (
            "SARIF: Segment Anything for Robust Image Forensics",
            "Image forgery localization remains challenging due to diverse manipulation "
            "techniques across benchmarks.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert result.negative_topic_penalty > 0, title


def test_2026_08_24_ai_generated_defects_are_demoted_on_industrial(app_config):
    """9849 (AGIDefect-4K) reached rank 2 of the 08-21 queue on a wrong sense.

    Its "defects" are generative artifacts in synthesised images, so it fired
    `defect`, `defect detection` and `defects` at once and landed on the
    Industrial Vision Inspection track. The per-track `ai-generated image`
    guard demotes rather than evicts — three positive matches outweigh the -12
    — but the combination with the global negatives moved it 46.8 -> 38.7.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "AGIDefect-4K: A Richly Annotated Dataset for AI-Generated Image Defect "
            "Detection, Localization and Explanation",
            "Generative AI can now produce highly realistic images, yet current models still "
            "exhibit subtle defects. AGIDefect-4K features hierarchical defect annotations "
            "with pixel-level segmentation masks localizing defective regions.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    control = classify_item(
        make_item(
            "Defect-4K: A Richly Annotated Dataset for Defect Detection, Localization and "
            "Explanation",
            "Manufacturing lines can now produce highly finished parts, yet current lines "
            "still exhibit subtle defects. Defect-4K features hierarchical defect "
            "annotations with pixel-level segmentation masks localizing defective regions.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert result.negative_topic_penalty > 0
    assert "Industrial Vision Inspection" in result.tracks
    # The guard demotes rather than evicts: same three `defect*` matches, but
    # 12 points lighter on the track that should not have claimed it.
    assert result.relevance_score < control.relevance_score
    assert control.negative_topic_penalty == 0


def test_2026_08_24_clinical_guard_does_not_evict_real_inspection(app_config):
    """The `clinical` guard exists for medical papers riding `visual inspection`.

    9974 (X-LMC) reached rank 7 of the 08-19 queue because ASITN/SIR collateral
    grading "relies on manual, highly variable visual inspection". Pin both
    sides: the medical item is demoted on the track (rank 7 -> 9, 30.1 ->
    24.0), and a genuine inspection paper that never says "clinical" is
    untouched.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    medical = classify_item(
        make_item(
            "X-LMC: Cross-View Spatiotemporal Collateral Circulation Scoring from DSA",
            "Clinical LMC grading via the ASITN/SIR scale relies on manual, highly variable "
            "visual inspection of digital subtraction angiography.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    medical_control = classify_item(
        make_item(
            "X-LMC: Cross-View Spatiotemporal Collateral Circulation Scoring from DSA",
            "LMC grading via the ASITN/SIR scale relies on manual, highly variable "
            "visual inspection of digital subtraction angiography.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert medical.negative_topic_penalty > 0
    assert medical.relevance_score < medical_control.relevance_score

    industrial = classify_item(
        make_item(
            "CDGP: Contrastive Dual Gaussian Processes for Weakly Supervised Anomaly Segmentation",
            "Industrial visual inspection must both decide whether a product is defective "
            "and localize the defect, yet pixel-level masks are costly to collect at scale.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in industrial.tracks
    assert industrial.negative_topic_penalty == 0


def test_2026_08_24_visual_tokens_plural_is_the_clean_form(app_config):
    """Textbook broad-form trap: the singular forms hit the radar's own work.

    `visual token` (17 hits) hits kept 8733 "Visual Token Codec" and
    `token pruning` (17 hits) hits kept 8214 "Defect-Preserving Token Pruning
    for Efficient Zero-Shot ..." — an Evaluate item on this radar. Only the
    plural `visual tokens` (20 hits, 0 kept) is clean.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "visual tokens" in negatives
    for rejected in ("visual token", "token pruning", "inpainting", "quality assessment"):
        assert rejected not in negatives, rejected

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = classify_item(
        make_item(
            "Clustering and Token Denoising for Faster and More Robust VLMs",
            "The computational burden of processing up to 576 visual tokens makes edge "
            "deployment challenging, so we introduce a training-free token pruning "
            "algorithm.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert noise.negative_topic_penalty > 0

    kept = classify_item(
        make_item(
            "Keep the Needle, Prune the Haystack: Defect-Preserving Token Pruning",
            "Zero-shot industrial anomaly detection is slow at high resolution. We prune "
            "background patches while preserving the tokens that carry defect evidence.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in kept.tracks
    assert kept.negative_topic_penalty == 0


def test_2026_08_24_figurative_rejects_stay_out(app_config):
    """Phrases with a clean kept count that fail the figurative-usage grep.

    `manuscript` (9 hits, 0 kept) loses to "upon acceptance of this manuscript"
    and "in this manuscript we release two datasets"; `provenance` (7, 0) is
    used in the dataset-curation sense that an industrial dataset paper would
    also use; `no-reference` (5, 0) also appears as "requiring no reference
    photos"; `inverse problems` (5, 0) is legitimate vocabulary for inverse
    rendering and deflectometry, and one hit is electrical capacitance
    tomography, which is industrial sensing.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in (
        "manuscript",
        "provenance",
        "no-reference",
        "inverse problems",
        "hand pose",
        "human pose",
        "generative model",
        "reinforcement learning",
        "basketball",
        "grape",
    ):
        assert rejected not in negatives, rejected


def test_2026_08_25_llm_vocabulary_is_penalised(app_config):
    """The 08-22..08-24 residue was LLM vocabulary, not a new CV domain.

    Multimodal-LLM evaluation, LLM-agent orchestration, captioning and
    alignment/RLHF papers keep reaching the queues on incidental matches
    (`benchmark`, `dataset`, `deployment`) with no negative penalty at all.
    All nine phrases hit ZERO of the 477 kept items in the 2156-item corpus.
    """
    negatives = app_config.negative_topics.negative_topics
    for phrase in (
        "multimodal models",
        "multi-agent",
        "captioning",
        "caption",
        "instruction tuning",
        "reward model",
        "reward models",
        "preference optimization",
    ):
        assert phrase in negatives, phrase

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = classify_item(
        make_item(
            "OVIBench: Benchmarking Online Video Question Answering under Interruption",
            "Recent multimodal models are evaluated with an instruction tuning corpus and a "
            "reward model; we release a benchmark dataset for caption quality.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert noise.negative_topic_penalty > 0


def test_2026_08_25_bare_agent_forms_stay_out(app_config):
    """`multi-agent` is the narrow form; the bare forms hit our own work.

    `agent` (108 hits, 3 kept) and `agents` (91, 5) both hit the radar's own
    industrial anomaly-detection agents — 576 (AnomalyCLAW) and 1832
    (IndusAgent). Only the `multi-agent` compound is clean at 23/0.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in ("agent", "agents", "embodied", "world model", "world models"):
        assert rejected not in negatives, rejected

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    kept = classify_item(
        make_item(
            "IndusAgent: Open-Vocabulary Industrial Anomaly Detection with Agentic Tools",
            "We reinforce an agent that calls inspection tools to localize the defect on a "
            "manufactured part, improving anomaly detection on industrial surfaces.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in kept.tracks
    assert kept.negative_topic_penalty == 0


def test_2026_08_25_captions_plural_stays_out(app_config):
    """Broad-form trap again: `caption` is clean, `captions` is not.

    `captions` (35 hits, 1 kept) hits 8798 Ego-OSCAR, an open-hardware stereo
    capture system decided Prototype; the A/B confirmed it drops that item from
    rank 2 to rank 4 on 08-08. `caption` (28, 0) and `captioning` (29, 0) carry
    the class without touching it.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "captions" not in negatives
    assert "caption" in negatives
    assert "captioning" in negatives


def test_2026_08_25_sonar_closes_the_acoustic_marine_half(app_config):
    """`marine` and `underwater` leave sonar imaging unpenalised.

    `underwater` has now been probed and rejected three times (17 hits, 1 kept
    — 6161 Wat3R underwater 3D geometry). `sonar` is only 5 hits but all five
    are acoustic seabed imaging, which is not a radar domain.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "sonar" in negatives
    assert "underwater" not in negatives

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = classify_item(
        make_item(
            "Geometry-Driven Opti-Acoustic Co-Registration for Side-Scan Sonar",
            "Side-scan sonar is a primary modality for large-scale seabed mapping; we align "
            "acoustic and optical reconstruction across extreme viewpoints.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert noise.negative_topic_penalty > 0


def test_negative_topics_have_no_duplicate_forms(app_config):
    """A repeated negative topic silently inflates the penalty by +10.

    ``classify_item`` collects *every* matching entry into ``negative_keywords``
    and scores ``25 + (len(matches) - 1) * 10``, so listing a phrase twice
    double-counts it. `forgery` and `reward model` were each carried twice until
    2026-08-26 — item 10339 on 08-25 printed "Negative topics: forgery, forgery"
    in its rationale. The matcher normalizes ``[\\s-]+``, so `open source` and
    `open-source` would collide the same way; compare on the normalized form.
    """
    import collections
    import re

    def normalize(keyword: str) -> str:
        return " ".join(part for part in re.split(r"[\s-]+", keyword.casefold()) if part)

    counts = collections.Counter(
        normalize(topic) for topic in app_config.negative_topics.negative_topics
    )
    assert [topic for topic, n in counts.items() if n > 1] == []


def test_2026_08_26_world_modeling_gerund_is_the_separable_form(app_config):
    """`world model` / `world models` hit kept items; the gerund does not.

    `world model` (26 hits, 7 kept) and `world models` (30, 4) have each been
    probed and rejected twice — they hit 7921 (BWM simulator), 8493 (GAUGE
    physical-fidelity benchmark) and 9239 (ContactGuard). `world modeling`
    hits 12 Ignore and zero kept; all twelve are generative video world models.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "world modeling" in negatives
    assert "world model" not in negatives
    assert "world models" not in negatives

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = classify_item(
        make_item(
            "SANA-WM: Efficient Minute-Scale World Modeling with Hybrid Linear Diffusion",
            "We scale long-horizon world modeling by predicting latent states, and evaluate "
            "the generated rollouts on a video benchmark.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert noise.negative_topic_penalty > 0


def test_2026_08_26_astronomy_object_vocabulary(app_config):
    """`astronomy` / `astronomical` miss sky-survey abstracts entirely.

    Item 10317 ("Decoupling candidate dual AGN ... in the GOTHIC survey")
    reached rank 23 on 08-25 with a zero penalty *and* matched the Industrial
    Vision Inspection track on `inspection` / `visual inspection` used in the
    astronomical sense. `galaxy` is rejected for polysemy — it hits "Samsung
    Galaxy S21 Ultra" as the reference device of an INT8 depth-latency paper.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "galactic" in negatives
    assert "galaxies" in negatives
    assert "galaxy" not in negatives

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = classify_item(
        make_item(
            "Decoupling candidate dual AGN from chance superpositions in the GOTHIC survey",
            "Dual active galactic nuclei mark a critical phase in the evolution of merging "
            "galaxies and the pairing of supermassive black holes, yet they remain difficult "
            "to identify in large imaging surveys; visual inspection of each candidate is "
            "infeasible at this scale.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert noise.negative_topic_penalty > 0

    kept = classify_item(
        make_item(
            "INT8 Quantization for Real-Time Monocular Depth on Mobile Hardware",
            "On a reference device (Samsung Galaxy S21 Ultra), INT8 quantization reduces "
            "depth latency for on-device deployment without measurable accuracy loss.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert kept.negative_topic_penalty == 0


def test_2026_08_26_retrieval_class_is_penalised(app_config):
    """Retrieval / RAG papers rode `dataset` + `benchmark` in with no penalty.

    10338 (cross-modal hashing) and 10333 (WeMM-Embedding) both landed in the
    08-25 queue at zero penalty. `image retrieval` 12 hits, `retrieval-augmented`
    12, `cross-modal retrieval` 4 — all zero kept.
    """
    negatives = app_config.negative_topics.negative_topics
    for phrase in ("image retrieval", "cross-modal retrieval", "retrieval-augmented"):
        assert phrase in negatives, phrase

    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    noise = classify_item(
        make_item(
            "Kent-Distribution Proxies for Large-Scale Cross-Modal Retrieval",
            "Supervised proxy-based deep cross-modal hashing dominates large-scale image "
            "retrieval; we evaluate on a standard benchmark dataset.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert noise.negative_topic_penalty > 0


def test_2026_08_26_hand_object_narrow_form_only(app_config):
    """The bare `hand-object` form hits a kept item; the compound does not.

    `hand-object` (10 hits, 1 kept) hits 9280, an RGB-D human-to-robot handover
    paper decided Watch. `hand-object interaction` (7, 0) carries the class.
    Singular and plural are separate regexes under the whole-word matcher, so
    `human video` and `human videos` are both carried.
    """
    negatives = app_config.negative_topics.negative_topics
    assert "hand-object interaction" in negatives
    assert "hand-object" not in negatives
    assert "human video" in negatives
    assert "human videos" in negatives


def test_2026_08_26_industrial_wrong_sense_phrases_stay_out(app_config):
    """Clean kept counts are not enough when the phrase can fire on our domain.

    `tampering` (3) and `forged` collide with anti-counterfeit / tamper-evident
    inspection and with forged metal parts; `engagement` (5) collides with gear
    and tool engagement; `photometric` (18 hits, 17 kept) is photometric stereo,
    a core radar topic. There is no per-item exemption mechanism, so these are
    rejected despite the Ignore hits.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in ("tampering", "forged", "engagement", "photometric"):
        assert rejected not in negatives, rejected


def test_2026_08_28_document_ai_and_agronomy_negatives(app_config):
    """The 08-26 / 08-27 misfires: three classes that reached queues unpenalised.

    10420 (AraMS-28k, historical Arabic manuscripts) rank 8, 10438 (tea leaf
    disease) rank 2 and 10534 (CropCop plant health) rank 6 all carried a ZERO
    penalty: `handwritten` / `handwriting` / `document understanding` miss a
    manuscript-transcription paper, and `plant disease` / `plant species` /
    `phenotyping` miss both "leaf disease" and "plant-health".
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    for title, summary in (
        (
            "AraMS-28k: A Line-Level Dataset of Historical Arabic Manuscripts",
            # Plural only on purpose: the whole-word matcher treats the two
            # forms as separate regexes, so both are configured.
            "Because reference transcriptions are fully vocalised, the corpus supports "
            "reading-order recovery and layout analysis.",
        ),
        (
            "Cross-Architecture Knowledge Distillation for Tea Leaf Disease Classification",
            "We distill a vision foundation model into a lightweight visual state space "
            "model for leaf disease classification and edge deployment.",
        ),
        (
            "CropCop: An Auditable 120-Class Plant-Health Model",
            "A plant health score can appear precise while resting on duplicated image "
            "families and a runtime file that was never evaluated.",
        ),
        (
            "AesCanvas: A Large-Scale Dataset for Aesthetic Critique",
            "We benchmark aesthetic quality judgement and contextual suitability of "
            "generated images.",
        ),
        (
            "DeCO: Discriminative Evidence Composition for Fine-Grained Dataset Distillation",
            "Dataset distillation compresses a large training set into a compact synthetic "
            "set while preserving downstream utility.",
        ),
    ):
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert result.negative_topic_penalty > 0, title


def test_2026_08_28_broad_and_figurative_forms_stay_out(app_config):
    """The rejected half of the same round.

    `manuscript` is clean on counts (12 Ignore, 0 kept) but three of those hits
    are the meta-usage "in this manuscript we release ...", which any on-domain
    paper may use about itself. `text recognition` (15/2) hits 6235 FedTR,
    industrial visual inspection; `aesthetics` (12/1) hits 516 BabelDOC;
    `crop disease` (1/1) hits 4395 HERCULES, agricultural robotics.
    """
    negatives = app_config.negative_topics.negative_topics
    for rejected in ("manuscript", "text recognition", "aesthetics", "crop disease"):
        assert rejected not in negatives, rejected
    assert "transcription" in negatives
    assert "aesthetic" in negatives


def test_2026_08_28_transcription_guards_the_industrial_track(app_config):
    """10420 reached the Industrial track on `quality control` in the editorial sense.

    What is quality-controlled is the manuscript's transcriptions, not a part.
    The global negative alone left it mid-queue; the per-track guard is what
    evicts the track match. A real inspection paper is untouched.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    document = classify_item(
        make_item(
            "AraMS-28k: A Line-Level Dataset of Historical Arabic Manuscripts",
            "Transcription and quality control of every line were performed by two "
            "annotators, and reference transcriptions are fully vocalised.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" not in document.tracks
    assert document.negative_topic_penalty > 0

    industrial = classify_item(
        make_item(
            "Automatic Weld Seam Segmentation for Industrial Quality Control",
            "Visual inspection of welded assemblies remains one of the least automated "
            "stages in many industrial production processes.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in industrial.tracks
    assert industrial.negative_topic_penalty == 0


def test_2026_08_28_weak_positive_keywords_are_kept(app_config):
    """`test set`, `sam` and `clip` all sit below the base keep rate and all stay.

    Removing `test set` looked free over 27 days but reproduced its original
    rejection over a quarter (7192 dropped, 7928 Prototype 11 -> 21); `sam`
    evicts 10549, the same day's zero-shot inspection paper decided Evaluate;
    `clip` evicts 9146. Below the base rate is a reason to measure, not to cut.
    """
    keywords = {track.name: set(track.positive_keywords) for track in app_config.topics.tracks}
    assert "test set" in keywords["Datasets & Benchmarks"]
    assert {"sam", "clip"} <= keywords["Vision Foundation Models"]
