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
    # The 2026-08-18 round deleted `computed tomography` because it hit three
    # kept industrial-XCT items. The exemption mechanism reaches that outcome
    # without giving up the phrase: it stays listed, guarded by the industrial
    # markers, so a medical CTA paper like this one is still penalised while
    # 1348 / 7081 / 9260 are not. See the `exemptions:` block.
    assert "computed tomography" in app_config.negative_topics.negative_topics
    assert "computed tomography" in result.negative_keywords
    assert "liver" in result.negative_keywords
    assert "clinically" in result.negative_keywords
    assert "clinical" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_bare_multimodal_no_longer_matches_foundation_track(app_config):
    """Anchor: 2026-07-08 backfill curation (07-03..07-07).

    Bare `multimodal` matched 26 Ignore items and 0 promotions — it fired the
    Vision Foundation Models track on generic VLM/MLLM benchmarks (e.g. CMDR,
    a multimodal document-retrieval benchmark) that carry no CV-engineering
    path. The breadth noise is already partly caught by the `multimodal large
    language` / `omnimodal` negatives; dropping bare `multimodal` from the track
    stops a document-retrieval benchmark from claiming a foundation-model match.
    """
    item = make_item(
        "CMDR: A Benchmark for Contextual Multimodal Document Retrieval",
        "We introduce CMDR, a benchmark for multimodal document retrieval that "
        "evaluates retrieval over interleaved text-and-image documents.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Vision Foundation Models" not in result.tracks
    assert result.recommended_ring == "Ignore"


def test_genuine_foundation_model_paper_still_matches_track(app_config):
    """Guard: dropping bare `multimodal` must not touch real foundation-model
    work — sam / dinov2 / clip / vision foundation model still fire."""
    item = make_item(
        "Adapting SAM and DINOv2 for Industrial Anomaly Detection",
        "We adapt the SAM vision foundation model together with DINOv2 features "
        "for zero-shot industrial anomaly detection and surface inspection.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Vision Foundation Models" in result.tracks
    assert "Industrial Vision Inspection" in result.tracks
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_deepfake_forensics_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-08 backfill candidate 5718 (VendorBench-100).

    VendorBench-100 is a deepfake image-detection benchmark that floated to a
    suggested Watch (final 45) purely on `benchmark` / `dataset` / `github` /
    `leaderboard` matches. Media-forensics / deepfake detection is outside the
    industrial-CV radar; the `deepfake` negative topic fires on the forensics
    task and drops the recommended ring back to Ignore.
    """
    item = make_item(
        "VendorBench-100: A Cross-Paradigm Benchmark for Deepfake Image Detection",
        "We present VendorBench-100, a benchmark and dataset for deepfake image "
        "detection across 100 generators, with a public leaderboard. Code is "
        "available at https://github.com/example/vendorbench.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "deepfake" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_synthetic_data_track_survives_deepfake_negative_topic(app_config):
    """Guard: the deepfake/forensics negatives must not touch a legitimate
    synthetic-data paper — the Synthetic Data & Simulation track keys off the
    two-word `synthetic data` phrase, not the forensics `synthetic image`."""
    item = make_item(
        "Domain-Randomized Synthetic Data for Industrial Defect Detection",
        "We build a rendering pipeline that produces synthetic data with domain "
        "randomization and sim-to-real transfer for surface defect detection and "
        "visual inspection on a calibrated industrial camera.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Synthetic Data & Simulation" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_medical_image_segmentation_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-08 daily run (items 6134 HPR-SAM, 6128 TRACE-Seg3D).

    Two SAM-based medical-segmentation papers reached the top-25 queue with a
    *zero* negative penalty — they matched the Vision Foundation Models track
    via `sam` plus `benchmark` / `github`, and the older `medical imaging` /
    `medical segmentation` negatives missed the phrase these abstracts use:
    "medical image segmentation". The negative fires on the task and keeps the
    recommended ring at Ignore.

    2026-08-05: the phrase was shortened to the bare `medical image`, which
    strictly subsumes it — see
    `test_medical_image_subsumes_the_two_longer_medical_phrases`.
    """
    item = make_item(
        "HPR-SAM: Prompt-free SAM for Medical Image Segmentation",
        "We adapt the Segment Anything Model (SAM) for automatic medical image "
        "segmentation of anatomical structures, evaluated on public benchmarks. "
        "Code is available at https://github.com/example/hpr-sam.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "medical image" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_ultrasound_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-08 daily run (items 6103 EP-SAM, 6084 SonoRank).

    An ultrasound-segmentation paper and a forearm-ultrasound prosthetics paper
    both queued with no negative penalty. `ultrasound` is medical-imaging noise
    for this optical-CV radar; no positive keyword contains it, so the
    whole-word negative fires only on genuine ultrasound work.
    """
    item = make_item(
        "EP-SAM: Edge-aware Prompt-enhanced SAM for Ultrasound Image Segmentation",
        "Ultrasound image segmentation delineates anatomical structures and "
        "lesions; we adapt SAM with edge-aware supervision, evaluated on "
        "multiple benchmarks.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "ultrasound" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_industrial_segmentation_survives_medical_negative_topics(app_config):
    """Guard: the medical negatives must not touch a legitimate industrial
    inspection paper. `medical image segmentation` is a full phrase (industrial
    work says defect / anomaly / surface segmentation) and `ultrasound` is a
    whole word absent from optical inspection abstracts."""
    item = make_item(
        "Anomaly Detection and Surface Inspection for Industrial Visual Inspection",
        "We present a defect detection and anomaly detection method for surface "
        "inspection in industrial visual inspection with machine vision and "
        "quality control, on a public benchmark dataset with code on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_vehicle_reid_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-09 daily run candidate 6227 (EV-MoE multi-query vehicle
    ReID + LCRI-1K benchmark).

    The paper reached rank 3 (final 41.8) on a *false* 3D Geometry &
    Reconstruction track match — its `multi-view` / `reconstruction` hits are
    ReID feature-fusion terms, not 3D geometry — plus Open-Source CV Tooling
    (github) and Datasets & Benchmarks. No ReID keyword fired because the
    abstract uses the "ReID" abbreviation, so the older `person re-identification`
    negative missed it. The vehicle-specific `vehicle reid` negative fires on the
    surveillance-retrieval task and drops the recommended ring back to Ignore.
    """
    item = make_item(
        "Mixture of Enhanced-View Experts for Multi-Query Vehicle ReID and A Large-Scale Benchmark",
        "We present a Mixture of Enhanced-View Experts for robust multi-query "
        "vehicle ReID, fusing multi-view features with reconstruction "
        "constraints, and collect a large-scale vehicle ReID benchmark. Code is "
        "available at https://github.com/example/ev-moe.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "vehicle reid" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_multi_object_tracking_reid_survives_vehicle_reid_negative(app_config):
    """Guard: the vehicle-specific ReID negative must NOT touch a legitimate
    multi-object-tracking paper that uses re-identification as an association
    component. The Object Tracking track keeps bare `re-identification` as a
    positive keyword by design, and the negative is scoped to the two-word
    `vehicle reid` / `vehicle re-identification` phrases, which a generic MOT
    abstract does not contain."""
    item = make_item(
        "Robust Multi-Object Tracking with Re-Identification-Based Association",
        "We propose a multi-object tracking method that uses a re-identification "
        "head for temporal association across frames, improving identity "
        "preservation under occlusion. Code is available at "
        "https://github.com/example/mot-reid.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Object Tracking" in result.tracks
    assert "re-identification" in result.positive_keywords
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_egocentric_human_pose_is_a_known_uncovered_gap(app_config):
    """Anchor: 2026-07-10 candidate 6284 (TSR-Ego), egocentric 3D human pose.

    This started life as a test that `human pose` and `egocentric` demote the
    paper. Both phrases were later re-probed against the full 2342-item decided
    corpus and both hit kept items — `human pose` hits 3488 (in-cabin occupant
    monitoring) and 10540 (human-robot action anticipation); `egocentric` hits
    nine, including 826/803 (egocentric hand-pose rigs) and 1000 (LEXI-SG).
    Per the project rule that a negative touching a kept item is rejected, both
    were dropped, which leaves TSR-Ego uncovered.

    Pinned as a gap rather than deleted: the scoped `human <x>` family still
    covers meshes, motion and video, and this records why the pose sub-case is
    knowingly not covered. The exemption mechanism is the obvious future fix —
    guard `human pose` on `in-cabin` / `human-robot` and it could come back.
    """
    item = make_item(
        "TSR-Ego: Temporally Guided Stereo Refinement for Egocentric 3D Human Pose Estimation",
        "Egocentric 3D human pose estimation from head-mounted stereo cameras is "
        "challenging due to fisheye distortion, severe self-occlusion, and "
        "truncation of body joints. We propose a temporally guided stereo "
        "framework that refines learned 3D joint queries with fisheye deformable "
        "stereo cross-attention, achieving state-of-the-art on UnrealEgo2.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    negatives = app_config.negative_topics.negative_topics
    assert "human pose" not in negatives
    assert "egocentric" not in negatives
    assert "human mesh" in negatives
    assert "human motion" in negatives
    # The positive side must survive: this is why the bare forms were refused.
    assert "Calibration & Camera Models" in result.tracks
    assert "pose estimation" in result.positive_keywords


def test_human_mesh_recovery_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-10 daily run candidate 6299 (DETRAM).

    DETRAM is an end-to-end multi-person human mesh recovery + tracking paper
    that queued with a zero negative penalty — it matched the 3D Geometry +
    Object Tracking tracks via `reconstruction` / `tracking`. HMR is human-body
    CV, out of scope; the `human mesh` negative fires on the task.
    """
    item = make_item(
        "DETRAM: End-to-end Detection, Tracking and Recovery of Human Meshes",
        "In the task of human mesh recovery, multi-person scenes are difficult "
        "due to occlusions between entities over time. DETRAM unifies detection, "
        "reconstruction, and tracking of humans with a single transformer "
        "decoder, achieving state-of-the-art tracking on PoseTrack21 and 3DPW.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "human mesh" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_human_motion_generation_papers_get_negative_penalty(app_config):
    """Anchor: recurring human-motion-generation class (e.g. 2026-07-09 ARDY,
    "Autoregressive Diffusion ... for Interactive Human Motion Generation").

    Human motion generation / prediction is human-body CV that recurs in the
    candidate queues via `reconstruction` / `tracking` / `diffusion`. The
    `human motion` negative fires on the task; it does not collide with the
    `motion model` or `structure from motion` positive keywords (distinct
    phrases).
    """
    item = make_item(
        "ARDY: Autoregressive Diffusion with Hybrid Representation for "
        "Interactive Human Motion Generation",
        "We present ARDY, an autoregressive diffusion framework for interactive "
        "human motion generation, producing coherent full-body human motion "
        "sequences conditioned on user input, with state-of-the-art motion "
        "quality on standard benchmarks.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "human motion" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_camera_pose_estimation_survives_human_negatives(app_config):
    """Guard: the human-centric negatives must NOT touch a genuine camera
    calibration / pose-estimation paper. `pose estimation`, `pose refinement`
    and `motion model` stay POSITIVE keywords; the negatives are scoped to the
    two-word `human pose` / `human mesh` / `human motion` phrases (plus
    `egocentric`), which a camera-geometry abstract does not contain."""
    item = make_item(
        "Robust Camera Pose Estimation for Multi-View 3D Reconstruction",
        "We estimate camera pose via bundle adjustment with epipolar geometry "
        "and pose refinement over a multi-view structure-from-motion pipeline, "
        "improving intrinsic calibration and 3D reconstruction accuracy for "
        "industrial cameras.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Calibration & Camera Models" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_video_llm_benchmark_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-13 daily run candidate 6395 (Do Video-LLMs Actually Watch?).

    The paper is a video-LLM character-tracking *diagnostic benchmark* that
    reached the top-25 with a *zero* negative penalty and a *false* Object
    Tracking track match — it matched `tracking` on "character-tracking" (a
    Video-LLM evaluation term, not multi-object tracking), plus Open-Source CV
    Tooling (toolkit) and Datasets & Benchmarks. Video-LLM evaluation is outside
    the industrial-CV radar; the `video large language` negative fires on the
    genre (dropping the trailing "model(s)" so both forms match) and drops the
    recommended ring to Ignore.
    """
    item = make_item(
        "Do Video-LLMs Actually Watch? Diagnosing Character-Tracking Failures in Long-Form Video",
        "Can a Video Large Language Model (Video-LLM) follow one person through a "
        "long video? Benchmarks increasingly score this kind of task. We test "
        "three open-source Video-LLMs with a nine-condition diagnostic protocol "
        "and release a toolkit for auditing what such benchmark scores measure.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "video large language" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_video_question_answering_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-13 daily run candidate 6323 (Evidence-Backed Video QA).

    A video-LLM question-answering paper (E-VQA, ST-Evidence benchmark) that
    piggy-backed on `benchmark` / `dataset` / `github` matches. Both the
    `video large language` and the question-answering negatives fire and keep
    it in Ignore.

    2026-07-27: `video question answering` was widened to bare `question
    answering` (35 Ignore / 0 kept over the decided corpus, and a strict
    superset of the old phrase), so this anchor now pins the short form.
    """
    item = make_item(
        "Evidence-Backed Video Question Answering",
        "Current Video Large Language Models (Video LLMs) excel in question "
        "answering but operate as black boxes. We propose Evidence-Backed Video "
        "Question Answering (E-VQA) and introduce ST-Evidence, a human-verified "
        "benchmark. Code and data are available at https://github.com/example/evqa.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "question answering" in result.negative_keywords
    assert "video large language" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_video_object_tracking_survives_video_llm_negatives(app_config):
    """Guard: the video-LLM negatives must NOT touch a genuine video
    object-tracking / detection paper. The negatives are scoped to the
    `video large language` / `video question answering` phrases; a real MOT or
    RGBT video-object-detection abstract does not contain them, and the Object
    Tracking track keeps its `tracking` / `object tracking` /
    `re-identification` positives intact."""
    item = make_item(
        "Robust Multi-Object Tracking in Video via Appearance Re-Identification",
        "We propose an online multi-object tracker for video that associates "
        "detections across frames using an appearance re-identification head and "
        "a Kalman filter for real-time object tracking. Code is available at "
        "https://github.com/example/video-mot.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Object Tracking" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_healthcare_training_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-13 daily run candidate 6325 (LoRA cascaded multimodal
    fusion for action recognition in healthcare/nurse-training environments).

    The paper slipped into the top-25 with a *zero* negative penalty: the
    existing medical negatives (`medical imaging` / `medical image segmentation`
    / `clinical` / `surgical` / `computed tomography`) all missed it because the
    abstract frames the domain as "healthcare-oriented training environments",
    not medical *imaging*. The `healthcare` negative fires and drops the ring to
    Ignore.
    """
    item = make_item(
        "LoRA Cascaded Multimodal Fusion for Action Recognition in Medical Training",
        "We present a cascaded LoRA-based multimodal fusion framework for action "
        "and activity recognition in healthcare-oriented training environments. "
        "We evaluate on two healthcare-oriented training environment datasets: "
        "NurViD and the Nurse Training dataset.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "healthcare" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_dermatology_generation_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-14 daily run candidate 8 (6425 cgDDI).

    A controllable *dermatological* imagery-generation paper for malignancy
    classification reached the top-25 with a *zero* negative penalty — it
    matched only Datasets & Benchmarks / Open-Source CV Tooling via
    `benchmark` / `dataset` / `github`, and no medical negative covered the
    skin/dermatology domain. The `dermatological` negative fires on the task and
    drops the recommended ring to Ignore.
    """
    item = make_item(
        "Controllable Generation of Diverse Dermatological Imagery for Malignancy Classification",
        "Accurate dermatological diagnosis requires equitable performance across "
        "diverse skin tones. We introduce cgDDI, a framework that synthesizes "
        "realistic skin samples and maps rare lesions onto novel skin-tones. We "
        "validate malignancy classification on the DDI benchmark and openly "
        "release synthetic images and code at https://github.com/example/cgDDI.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "dermatological" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_dermatology_reconstruction_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-14 daily run candidate 1 (6423 DermDepth), which floated
    to RANK 1 (final 42.45) on only the `clinical` hit.

    A monocular metric-scale 3D reconstruction paper for the *dermatology*
    domain. The metric-scale technique is metrology-adjacent, but the dataset
    (D-Synth) and benchmarks are dermatological. The `dermatology` /
    `dermatological` negatives fire on the domain — a real calibration / 3D
    paper never says "dermatology".
    """
    item = make_item(
        "DermDepth: Monocular Metric Scale 3D Reconstruction for Dermatology",
        "We present DermDepth, the first single-view metric scale 3D "
        "reconstruction model for the dermatological domain, and D-Synth, a "
        "synthetic dermoscopic dataset with pixel-perfect 3D information for skin "
        "cancer screening. Code and models are available on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "dermatology" in result.negative_keywords
    assert "dermatological" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_computational_pathology_wsi_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-14 daily run candidate 12 (6469 CGRL).

    A *computational pathology* / *whole-slide image* classification paper
    (TCGA-BRCA/NSCLC) reached the top-25 with a *zero* negative penalty: the
    existing `histopathology` negative did not fire because the abstract says
    "computational pathology" and "whole-slide image", not "histopathology".
    The `computational pathology` and `whole-slide` negatives fire on the task
    and keep it in Ignore. (`whole-slide image` was the original phrase; it was
    shortened on 2026-07-30 because the whole-word matcher missed 7621, whose
    abstract says "whole-slide images".)
    """
    item = make_item(
        "CGRL: Concept-Guided Representation Learning for Whole-Slide Image Classification",
        "Weakly supervised whole-slide image (WSI) classification is widely used "
        "in computational pathology because slide-level labels are easier to "
        "obtain than dense annotations. We evaluate CGRL on the TCGA-BRCA and "
        "TCGA-NSCLC datasets using multiple instance learning baselines.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    # `computational pathology` was retired on 2026-07-31 in favour of the bare
    # `pathology`, which subsumes it — 7829 says "pathology foundation models".
    assert "pathology" in result.negative_keywords
    assert "computational pathology" not in result.negative_keywords
    assert "whole-slide" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


def test_industrial_reconstruction_survives_dermatology_pathology_negatives(app_config):
    """Guard: the dermatology / pathology negatives must NOT touch a genuine
    industrial 3D-reconstruction / surface-inspection paper. The phrases are
    medical-specific (`dermatology` / `dermatological` / `computational
    pathology` / `whole-slide`); an industrial abstract about defect /
    surface reconstruction does not contain them."""
    item = make_item(
        "Metric 3D Reconstruction for Surface Defect Inspection on a Calibrated Camera",
        "We reconstruct metric 3D surface geometry from a calibrated industrial "
        "camera for defect detection and surface inspection, using bundle "
        "adjustment and structure from motion. Code is available on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_wildlife_ecology_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-22 backfill (07-15..07-21), the largest uncovered noise
    class of the window — 6745 NACTI camera-trap species recognition, 6808
    leprosy in wild chimpanzees, 6887 AnimalCLEF animal ReID, 6807 PanAf-SBR
    great-ape behaviour. All reached the top-25 with a *zero* negative penalty,
    riding `benchmark` / `dataset` / `re-identification` matches."""
    item = make_item(
        "Benchmarking NACTI Species Recognition in Long-Tailed Regimes",
        "We benchmark species recognition on camera trap imagery collected for "
        "wildlife monitoring and biodiversity assessment, releasing a dataset "
        "and evaluation code on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "camera trap" in result.negative_keywords
    assert "wildlife" in result.negative_keywords
    assert "species recognition" in result.negative_keywords
    assert "biodiversity" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_agriculture_phenotyping_papers_get_negative_penalty(app_config):
    """Anchor: 6707 (tomato phenotyping via procedural synthetic data) and 6655
    (Delineate Anything v2 global field delineation) — both reached RANK 2 of
    their day with a zero penalty, the two highest-scoring noise items of the
    2026-07-22 backfill window."""
    phenotyping = make_item(
        "Text-conditioned Segmentation for Tomato Phenotyping via Procedural Synthetic Data",
        "We generate procedural synthetic data to train a segmentation model for "
        "tomato phenotyping, and release the simulation pipeline and dataset.",
    )
    delineation = make_item(
        "Delineate Anything v2: A Global Foundation Model for Field Delineation",
        "Agricultural field boundary delineation is a foundational task. Our "
        "foundation model handles cropland texturing patterns at national scale, "
        "with a benchmark and weights on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    for item, phrase in ((phenotyping, "phenotyping"), (delineation, "cropland")):
        result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
        assert phrase in result.negative_keywords
        assert result.recommended_ring == "Ignore"


def test_affect_recognition_papers_get_negative_penalty(app_config):
    """Anchor: 6933 ambivalence/hesitancy recognition, 6733 SpEmoC emotion
    benchmark and 6860 facial action unit detection, all zero-penalty in the
    2026-07-22 backfill window. The phrase-level negatives are narrower than the
    pre-existing `face recognition` negative, not a duplicate of it. On
    2026-07-23 `facial expression` / `facial action unit` were consolidated into
    bare `facial`, so one abstract now contributes one match, not two."""
    item = make_item(
        "SpEmoC: A Balanced Speaker-Segment Multimodal Emotion Benchmark",
        "We study affective behaviour analysis, combining emotion recognition "
        "with facial expression and facial action unit cues, and release the "
        "benchmark and dataset on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "emotion recognition" in result.negative_keywords
    assert "facial" in result.negative_keywords
    assert "affective" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_handwriting_ocr_papers_get_negative_penalty(app_config):
    """Anchor: 6557 Devanagari handwriting recognition, 6917 handwritten vs
    printed text segmentation and 6970 cross-lingual handwritten OCR, all
    zero-penalty across the 2026-07-22 backfill window."""
    item = make_item(
        "Barnamala: Parameter-Efficient Handwritten Devanagari Recognition",
        "We study handwritten script recognition and optical character "
        "recognition at benchmark saturation, releasing code on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "handwritten" in result.negative_keywords
    assert "optical character recognition" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_uncovered_medical_modalities_get_negative_penalty(app_config):
    """Anchor: 6983 echocardiography, 6974 screening mammography and 6699
    breast-MRI classification reached the top-25 at zero penalty because the
    existing medical negatives name neither the modality nor these organs."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Motion-Conditioned Multi-View Fusion for Myocardial Infarction Localization",
            "We fuse multi-view echocardiography sequences and release a dataset.",
            "echocardiography",
        ),
        (
            "Dataset-Origin Signatures and Shortcut Learning in Screening Mammography AI",
            "A cross-dataset benchmark of screening mammography models.",
            "mammography",
        ),
        (
            "Cross-Dataset Generalization in Breast MRI Tumor Classification",
            "We study class-wise dataset mixing for breast MRI tumor classification.",
            "mri",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords
        assert result.recommended_ring == "Ignore"


def test_industrial_xct_defect_paper_is_exempt_from_computed_tomography(app_config):
    """Anchor: 2026-07-15 candidate 17 (7081 XCT-SAM). Defect segmentation on
    additive-manufacturing X-ray CT lost 25 points to the *medical* `computed
    tomography` negative. Industrial XCT is NDT inspection, not radiology, so
    the exemption guards must suppress the penalty entirely."""
    item = make_item(
        "XCT-SAM: Domain Adaptation of SAM for Industrial XCT Defect Segmentation",
        "Defect segmentation in additive manufacturing X-ray computed tomography "
        "images remains challenging due to class imbalance. We adapt SAM with "
        "Conv-LoRA adapters and release the dataset on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "computed tomography" not in result.negative_keywords
    assert result.negative_topic_penalty == 0


def test_semiconductor_inspection_paper_is_exempt_from_super_resolution(app_config):
    """Anchor: 2026-07-19 candidate 17 (6806). A low-false-call semiconductor
    inspection benchmark lost 25 points to the generic `super-resolution`
    negative, even though its finding argues *against* SR in inspection
    pipelines. Core-domain items must not be penalised for naming the technique
    they evaluate."""
    item = make_item(
        "Does Super-Resolution Preserve Defect Evidence? A Benchmark for Semiconductor Inspection",
        "Super-resolution can make inspection images appear sharper without "
        "preserving the evidence needed to detect a defect. We benchmark "
        "reconstruction against detection at a predeclared false-positive rate.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "super-resolution" not in result.negative_keywords
    assert result.negative_topic_penalty == 0


def test_exemptions_do_not_leak_to_medical_or_restoration_noise(app_config):
    """Guard on the guard: the `computed tomography` / `super-resolution`
    exemptions are scoped to industrial vocabulary, so ordinary medical-CT and
    image-restoration papers must keep their penalty."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    medical = make_item(
        "Anatomy-Aware 3D Mesh Refinement of Pericardium Segmentations",
        "We refine pericardium segmentations on computed tomography volumes for "
        "clinical use, releasing code on github.",
    )
    restoration = make_item(
        "DRIFT: Difficulty-aware Rectified Flows for Through-plane Super-Resolution",
        "We propose a rectified-flow model for through-plane super-resolution of "
        "volumetric scans, improving perceptual quality over prior baselines.",
    )
    for item, phrase in ((medical, "computed tomography"), (restoration, "super-resolution")):
        result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
        assert phrase in result.negative_keywords
        assert result.negative_topic_penalty > 0


def test_cardiovascular_magnetic_resonance_paper_gets_negative_penalty(app_config):
    """Anchor: 2026-07-22 candidate 2 (7138). A cardiac-disease diagnosis
    pipeline reached RANK 2 (final 41.1) at ZERO penalty — its abstract says
    "cardiovascular magnetic resonance", never "…imaging", and "clinically
    meaningful" rather than "clinical". Shortening the phrase to `magnetic
    resonance` and adding the adverb closes both halves of the gap."""
    item = make_item(
        "An Automated, Clinically Meaningful AI Tool for Diagnosing Cardiac Disease from CMR",
        "Cardiovascular magnetic resonance enables non-invasive assessment of "
        "myocardial structure. We fine-tune three vision foundation models and "
        "release weights and code on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "magnetic resonance" in result.negative_keywords
    assert "clinically" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_face_and_gaze_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-21 candidate 3 (6681 UVFaceFusion, final 40.9 at zero
    penalty) and candidate 9 (6678 gaze object prediction), plus 2026-07-22
    candidate 13 (7179 pain assessment from facial video). The `human pose` /
    `human mesh` negatives cover bodies, not faces; `face recognition` covers
    identification, not reconstruction."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "UVFaceFusion: Multi-view Topologically Consistent Face Reconstruction",
            "We reconstruct high-fidelity facial geometry with an assigned topology "
            "for digital avatar creation, fusing multi-view point maps in UV space. "
            "Code on github.",
            "facial",
        ),
        (
            "ReFace: Reorganizing Facial Spatiotemporal Representations for Pain Assessment",
            "Automatic pain assessment from facial video remains challenging. We "
            "evaluate on a benchmark dataset and report test set accuracy.",
            "facial",
        ),
        (
            "Open-Vocabulary Gaze Object Prediction: Benchmark and Method",
            "Gaze object prediction localizes the objects humans attend to. We "
            "introduce a benchmark and release code on github.",
            "gaze object",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords
        assert result.recommended_ring == "Ignore"


def test_geospatial_mapping_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-22 candidates 25 (7143 Sentinel-2 building detection),
    16 (7173 global building-footprint rasters) and 12 (7147 UAV-to-satellite
    geo-localisation), all zero-penalty because the abstracts never say "remote
    sensing"."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Toward Seasonal Guidelines for Sentinel-2 Building Detection",
            "We build a multi-temporal Sentinel-2 dataset and derive binary "
            "ground truth masks from a topographic database.",
            "sentinel-2",
        ),
        (
            "Global Building Area Estimation Products: How Accurate Are They?",
            "Geospatial rasters of building footprint area support monitoring "
            "urbanization and tracking greenhouse gas emissions. We evaluate four "
            "products against a manually labeled dataset.",
            "geospatial",
        ),
        # The third anchor of this round (7147, UAV-to-satellite geo-localisation)
        # is deliberately no longer covered. `satellite imagery`, `satellite`,
        # `satellite image` and `geo-localization` were all re-probed against the
        # full decided corpus and the family hits kept 27 (feedforward 3D from
        # satellite/street) and 6669 (NGPS GPS-denied aerial geo-localization).
        # `land cover` and `sea ice` are the scoped forms taken instead.
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords
        assert result.recommended_ring == "Ignore"


def test_image_compression_paper_does_not_match_fiducial_track(app_config):
    """Anchor: 2026-07-21 candidate 18 (6653). "Checkerboard context model" is
    learned-image-compression vocabulary, not a calibration target — the track
    guard must drop the Target Detection & Fiducials match entirely."""
    item = make_item(
        "Wavefront Parallelization for Efficient Learned Image Compression",
        "Autoregressive context models are foundational for learned image "
        "compression. Existing acceleration methods such as checkerboard context "
        "require retraining. Code on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Target Detection & Fiducials" not in result.tracks


def test_calibration_target_paper_still_matches_fiducial_track(app_config):
    """Guard on the guard: the compression phrases must not cost a real
    checkerboard-calibration paper its track."""
    item = make_item(
        "Robust Checkerboard Corner Detection for Industrial Camera Calibration",
        "We detect checkerboard corners at subpixel accuracy under motion blur "
        "and compare against ChArUco calibration target detection.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Target Detection & Fiducials" in result.tracks


def test_image_generation_benchmark_does_not_match_robotics_track(app_config):
    """Anchor: 2026-07-21 candidate 7 (6632 ExpertVerse). A knowledge-intensive
    image-generation benchmark matched Robotics Vision on "semantic
    manipulation" alone."""
    item = make_item(
        "ExpertVerse: A Benchmark for Expert-Level Reasoning in Visual Synthesis",
        "Instruction-based image generation has moved beyond semantic "
        "manipulation to knowledge-driven visual reasoning. We curate an "
        "open-source benchmark dataset.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Robotics Vision" not in result.tracks


def test_robot_manipulation_paper_still_matches_robotics_track(app_config):
    """Guard on the guard: a genuine robot-manipulation paper keeps its track."""
    item = make_item(
        "Visual Servoing for Bin-Picking Manipulation with a Calibrated Robot Arm",
        "We combine visual odometry and robotics manipulation planning to guide a "
        "robot arm toward randomly posed parts in a bin.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Robotics Vision" in result.tracks


def test_industrial_tracking_paper_survives_the_new_negatives(app_config):
    """Known false positive to protect: an industrial multi-object tracking /
    inspection paper must not pick up any of the wildlife, affect, OCR or
    medical-modality phrases added on 2026-07-22, nor the face/gaze, medical and
    geospatial phrases added on 2026-07-23."""
    item = make_item(
        "Real-Time Multi-Object Tracking of Parts on a Conveyor for Inline Inspection",
        "We track densely packed, visually similar parts on a conveyor using "
        "re-identification features and a calibrated industrial camera, and "
        "detect surface defects inline. Code is available on github.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Object Tracking" in result.tracks
    assert result.negative_topic_penalty == 0
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_biometric_identity_papers_get_negative_penalty(app_config):
    """Anchor: the 2026-07-23 queue held three biometric-identity papers at zero
    penalty (7283 finger-vein age/gender, 7212 iris recognition, 7261 text-based
    person retrieval) because `face recognition` covers one modality and
    `person re-identification` misses the "person retrieval" phrasing."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "MAGE-Vein: Multi-Instance Age and Gender Estimation from Finger Vein Images",
            "Age estimation from finger vein images has been considered impractical due to "
            "demographic biases in public datasets. Our code is available on github.",
        ),
        (
            "Towards Robust Iris Recognition Through Occlusion Identification",
            "Iris recognition identifies individuals using the stable texture of the iris. "
            "A diffusion model performs reconstruction of the occluded region.",
        ),
        (
            "Achieving Text-based Person Retrieval with Any Granularity",
            "Text-based person retrieval faces uncertainty of query granularity. We build a "
            "multi-grained dataset and an evaluation benchmark.",
        ),
        (
            "DINO-VPT: Visual Prompt Tuning for Joint Physical-Digital Face Anti-Spoofing",
            "We evaluate presentation attack detection under a unified protocol and release "
            "the benchmark on github.",
        ),
        (
            "Complex Structure Tensor Representations for Periocular Recognition",
            "We enhance CNNs for periocular verification on a biometrics benchmark.",
        ),
        (
            "Local Spatiotemporal Convolutional Network for Robust Gait Recognition",
            "Gait recognition identifies subjects at a distance from silhouette sequences.",
        ),
        (
            "A Prototypical Approach for Writer-Independent Offline Signature Verification",
            "Offline signature verification decides whether a questioned signature is genuine.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert result.negative_topic_penalty > 0, title
        assert result.final_score < app_config.scoring.thresholds.watch, title


def test_industrial_papers_survive_the_biometric_negatives(app_config):
    """Guard on the guard: the biometric phrases are modality-specific and must
    not touch on-radar work. `signature` alone would have hit the spectral-
    signature paper; `iris` alone would have hit the iris diaphragm."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Spectral Signature Matching for Multispectral Weld Seam Inspection",
            "We match the spectral signature of weld defects across bands using a calibrated "
            "industrial multispectral camera.",
        ),
        (
            "Lens Iris Aperture Calibration for Depth-from-Defocus Metrology",
            "We model how the iris aperture of the lens changes the point spread function "
            "during camera calibration for 3D measurement.",
        ),
        (
            "Template Retrieval for Part Identification in Bin Picking",
            "We retrieve the matching CAD template for each part and refine its 6-DoF pose "
            "for robot guidance, then verify the grasp with a calibrated industrial camera.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert result.negative_topic_penalty == 0, title


def test_generative_world_paper_does_not_match_robotics_track(app_config):
    """Anchor: 2026-07-23 candidate 12 (7215 GS-Agent). LLM-agent-driven 4D world
    creation matched Robotics Vision on "camera and lighting manipulation"."""
    item = make_item(
        "GS-Agent: Creating 4D Physical Worlds With Generative Simulation",
        "We present an end-to-end multi-agent framework for 4D world generation that covers "
        "3D asset curation, material tuning, placement, and rendering configuration, "
        "including camera and lighting manipulation.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Robotics Vision" not in result.tracks


def test_vlm_reasoning_benchmark_papers_get_negative_penalty(app_config):
    """Anchor: the 2026-07-27 mining pass over the decided corpus. Half the
    Ignore items still carried zero penalty, and the largest coherent class in
    that residue is the multimodal-LLM reasoning/QA benchmark — papers whose
    contribution is an evaluation of language grounding rather than of a
    measurement. The existing `vision-language` / `multimodal large language`
    negatives only catch the ones that name the architecture; these catch the
    ones that name the task."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Ground3D-LMM: Fine-Grained 3D Point Grounding with Large Multimodal Models",
            "We evaluate spatial reasoning over indoor point clouds and release a benchmark.",
            "spatial reasoning",
        ),
        (
            "Look Light, Think Heavy: What Multimodal Reasoning Can and Cannot Do",
            "We study multimodal chain-of-thought prompting across 12 benchmarks.",
            "chain-of-thought",
        ),
        (
            "PhysScene: A Scene Graph Dataset for Scientific Reasoning in Physics Experiments",
            "A dataset for visual reasoning about laboratory scenes, released on github.",
            "visual reasoning",
        ),
        (
            "Seeing Once is Enough? Geometry-Aware Token Pruning for 3D Scene Understanding",
            "We prune tokens for 3D question answering while preserving accuracy.",
            "question answering",
        ),
        (
            "Robo-Cortex: A Self-Evolving Agent via Dual-Grain Cognitive Memory",
            "We build an embodied agent that accumulates episodic memory across tasks.",
            "embodied agent",
        ),
        (
            "Parse, Search, and Confirmation: Training-Free Aerial Navigation with LLMs",
            "A training-free vision-and-language navigation pipeline for aerial agents.",
            "vision-and-language navigation",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords, f"{phrase!r} did not fire on {title!r}"
        assert result.recommended_ring == "Ignore"


def test_question_answering_widening_still_catches_video_qa(app_config):
    """`video question answering` was widened to bare `question answering` on
    2026-07-27. The widening must strictly subsume the old phrase — and must
    fire exactly once, so the item is not penalised twice for the same trait."""
    item = make_item(
        "Evidence-Backed Video Question Answering with Temporal Grounding",
        "We release a benchmark for long-video question answering with evidence spans.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "question answering" in result.negative_keywords
    assert result.negative_keywords.count("question answering") == 1
    assert "video question answering" not in result.negative_keywords


def test_core_domain_survives_the_vlm_reasoning_negatives(app_config):
    """Probe against kept items: none of the 2026-07-27 reasoning phrases may
    touch geometry, calibration, or robot-guidance work. `embodied`,
    `embodied ai`, `world model` and `success rate` were rejected precisely
    because they did — this pins the narrower replacements."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "EmbodiedGen V2: An Agentic, Simulation-Ready 3D World Engine for Embodied AI",
            "A generative engine producing simulation-ready 3D assets with physical scale "
            "for embodied AI research, released open-source.",
        ),
        (
            "Quantitative Video World Model Evaluation for Geometric-Consistency",
            "We evaluate whether video world models preserve geometric consistency under "
            "camera motion, using multi-view reconstruction as ground truth.",
        ),
        (
            "Category-Level 6D Pose Estimation for Bin Picking",
            "Our grasping pipeline raises the success rate on cluttered industrial bins "
            "using depth from a structured-light 3D sensor.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert result.negative_topic_penalty == 0, (
            f"{title!r} was penalised by {result.negative_keywords}"
        )


def test_medical_modality_tail_gets_negative_penalty(app_config):
    """Anchor: 2026-07-24 candidate 5 (7327 CARDIAG, coronary-angiography segment
    classification) reached rank 5 with zero penalty — none of `medical imaging`
    / `computed tomography` / `histopathology` / `surgical` / `clinical` / `mri`
    names angiography. Medical imaging keeps leaking one modality at a time, so
    the tail is closed by modality and clinical-entity name."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "CARDIAG: A Dense Segment Classification Benchmark for Coronary Angiography",
            "We benchmark deep architectures that densely classify pixels of angiography "
            "images, and release the dataset.",
            "angiography",
        ),
        (
            "Frozen Foundation-Model Embeddings Discard Small-Lesion Signal",
            "We show that frozen embeddings lose lesion-scale detail in chest radiography.",
            "lesion",
        ),
        (
            "A Leakage-Aware Comparative Benchmark for Outcome Prediction",
            "We evaluate leakage across patient-level splits and report calibrated metrics.",
            "patient",
        ),
        (
            "MS-rPPG: Multi-spectral State Space Model for Remote Photoplethysmography",
            "We estimate cardiac pulse from facial video under illumination change.",
            "cardiac",
        ),
        (
            "Dual-Stream Decoding for 3D Visual Perception",
            "We decode EEG signals recorded during 3D shape viewing, releasing the dataset.",
            "eeg",
        ),
        (
            "Computational Imaging Priors for Wireless Capsule Endoscopy",
            "Monte Carlo-guided reconstruction for capsule endoscopy video.",
            "endoscopy",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords, f"{phrase!r} did not fire on {title!r}"
        assert result.recommended_ring == "Ignore"


def test_industrial_ultrasonic_ndt_is_exempt_from_ultrasound(app_config):
    """`ultrasound` is medical sonography, but ultrasonic NDT is a core
    inspection modality. Industrial abstracts normally say "ultrasonic", which
    the whole-word matcher misses anyway; the guard covers the case where one
    says "ultrasound" instead."""
    item = make_item(
        "Automated Weld Defect Sizing from Phased-Array Ultrasound Volumes",
        "We segment planar defects in non-destructive ultrasound inspection of welds "
        "and compare against radiographic ground truth.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "ultrasound" not in result.negative_keywords


def test_ultrasound_exemption_does_not_leak_to_medical_sonography(app_config):
    """Guard on the guard: ordinary medical ultrasound keeps its penalty."""
    item = make_item(
        "Fetal Biometry Estimation from Obstetric Ultrasound Video",
        "We estimate standard planes from ultrasound sweeps acquired in routine screening.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "ultrasound" in result.negative_keywords


def test_visual_token_pruning_paper_does_not_match_edge_ai_track(app_config):
    """Anchor: 2026-07-25/26 queued five VLM token-efficiency papers (7504
    Omni-Prune, 7517, 7523, 7527, 7534). `pruning` is an Edge AI positive
    keyword, but these papers prune *visual tokens* out of an LLM context
    window, which has nothing to do with edge deployment."""
    item = make_item(
        "Omni-Prune: Query-Aware Unified Token Pruning for Efficient Omnimodal Models",
        "We reduce inference cost by dropping redundant visual tokens before the "
        "language decoder, applying query-aware token pruning at every layer.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Edge AI & Deployment" not in result.tracks


def test_network_pruning_paper_still_matches_edge_ai_track(app_config):
    """Guard on the guard: the token phrases must not cost a real model-compression
    paper its Edge AI track."""
    item = make_item(
        "Structured Pruning and INT8 Quantization for Real-Time Defect Detection",
        "We prune convolution channels and export to TensorRT, measuring latency "
        "on a Jetson Orin for inline inspection.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Edge AI & Deployment" in result.tracks


def test_content_generation_and_domain_negatives_fire(app_config):
    """Anchor: the 2026-07-25..27 backfill put five classes into the top-25 with
    zero negative penalty. One case per phrase added on 2026-07-28."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "SimBEV2X: A Large-Scale Dataset for Cooperative Perception",
            "We build a vehicle-to-everything (V2X) dataset in CARLA with lidar and "
            "camera streams from connected vehicles and roadside units.",
            "v2x",
        ),
        (
            "CoBEV: Bird's-Eye-View Fusion for Connected Vehicles",
            "Cooperative perception across multiple agents overcomes occlusion in "
            "urban driving, evaluated on a new benchmark.",
            "cooperative perception",
        ),
        (
            "Head Avatars with Dynamic Explicit Hair",
            "We reconstruct a photorealistic head avatar with strand-level hair from "
            "monocular video and render it in real time.",
            "head avatar",
        ),
        (
            "DreamStyle3D: Efficient 3D Stylized Asset Generation",
            "Our framework accelerates 3D content creation for gaming and virtual "
            "reality by disentangling style from geometry.",
            "3d content",
        ),
        (
            "Layering Virtual Try-On",
            "We synthesize layered clothing on a person image, preserving the "
            "occlusion order between shirt, jacket and coat.",
            "try-on",
        ),
        (
            "ESRVS: Extreme Semi-Supervised Retinal Vessel Segmentation",
            "Learning from minimal supervision is a long-standing goal in medical "
            "image analysis, where dense expert annotations are costly.",
            "medical image",
        ),
        (
            "Prototype Transfer for Coronary Vessel Segmentation",
            "We propagate labels across an unlabeled pool for vessel segmentation "
            "and report Dice on eight public datasets.",
            "vessel segmentation",
        ),
        (
            "JPEG AIC2026: A Dataset for Fine-Grained Assessment of Image Coding",
            "We cover artifacts from conventional and learned image compression "
            "codecs at twenty perceptually spaced distortion levels.",
            "image compression",
        ),
        (
            "Codebook Capacity Governs Perceptual Quality Across Resolutions",
            "We analyze the rate-distortion tradeoff of hierarchical discrete video "
            "codecs at matched bitrates.",
            "rate-distortion",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords, f"{phrase!r} did not fire on {title!r}"
        assert result.recommended_ring == "Ignore"


def test_core_domain_survives_the_2026_07_28_negatives(app_config):
    """The 2026-07-28 batch was probed against the decided corpus for kept-item
    collisions; these fixtures pin the ones that were close enough to reject a
    broader phrase (`avatar`, `retinal`, `3d asset`, `image quality assessment`,
    `garment`) and keep the surviving phrases honest."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Programmable Silicon Retina on a Pixel Processor Array",
            "We implement early vision on a focal-plane sensor processor, running "
            "convolution in the pixel array itself.",
        ),
        (
            "Articraft: An Agentic System for Scalable Articulated 3D Asset Generation",
            "We generate simulation-ready articulated assets with joint limits for "
            "robot manipulation training in a physics simulator.",
        ),
        (
            "A Reference-Free Framework for Evaluating Single-Frame ISP Pipelines",
            "We estimate full-reference image quality assessment metrics for a "
            "camera image signal processing pipeline from ISO metadata.",
        ),
        (
            "Automated Fabric Defect Detection for Garment Manufacturing Lines",
            "We detect weave defects on textile rolls with an industrial line-scan "
            "camera and report false-call rates on a production line.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert not result.negative_keywords, (
            f"{title!r} unexpectedly penalised by {result.negative_keywords}"
        )


def test_2026_07_30_negative_topics_fire(app_config):
    """Anchor: 18 of the 40 Ignore items across the 07-28 and 07-29 queues reached
    the top 25 carrying zero negative penalty. Each fixture below pins one of the
    classes mined out of that residue, using the phrasing the real abstracts
    used."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Group Equivariant Diffusion for Anomaly Detection in Computational Cytology",
            "Malignant cells are rare on whole-slide images, so we train on normal "
            "slide-negative patches and flag abnormal patches at test time.",
            "whole-slide",
        ),
        (
            "Foundation Model Embeddings for Distant Metastasis Prediction",
            "We predict distant metastasis risk in head and neck cancer from "
            "preoperative CT and compare against radiomics features.",
            "cancer",
        ),
        (
            "SciFigQual-Bench: A Benchmark for Scientific Figure Quality Assessment",
            "We score each scientific figure against its caption, citing sentence "
            "and surrounding manuscript context across five dimensions.",
            "scientific figure",
        ),
        (
            "BaFCo: A Benchmark for Complex Bangla Form Comprehension",
            "We evaluate layout-aware models on document understanding over "
            "scanned government forms.",
            "document understanding",
        ),
        (
            "Online Handwriting Trajectory Reconstruction from Kinematic Sensors",
            "We map the sensor signals of a digital pen to the online handwriting "
            "trajectory, aligning sampling rates with dynamic time warping.",
            "handwriting",
        ),
        (
            "MEDit-Bench: A Dataset for Message-Driven Narrative Video Editing",
            "The selected shots change with the narrative an editor wishes to "
            "convey, so we pair long-form videos with multiple editing messages.",
            "video editing",
        ),
        (
            "RDVSv2: A Large-scale Benchmark for RGB-D Video Salient Object Detection",
            "We release dense frame-level masks for salient object detection and "
            "fine-tune a SAM2 encoder on RGB, depth and optical flow.",
            "salient object detection",
        ),
        (
            "BG-REAL: A Real-Data Anchored Benchmark for Background Manipulation",
            "We package a benchmark for background manipulation detection and "
            "localization with matched authentic controls.",
            "manipulation detection",
        ),
        (
            "SARIF: Segment Anything for Robust Image Forensics",
            "We adapt a promptable segmentation backbone to image forensics and "
            "report pixel-level localization on spliced composites.",
            "image forensics",
        ),
        (
            "ReLATE: Reliability-Guided Evidence Fusion for UAV-Satellite Retrieval",
            "We benchmark robustness of cross-view geo-localization under 27 "
            "corruption types at three severity levels.",
            "cross-view geo-localization",
        ),
        (
            "A Unified Benchmark and Modality-Adaptive Network for Illumination Shift",
            "Existing drone-view geo-localisation benchmarks capture a single "
            "illumination condition and lack aligned infrared imagery.",
            "drone-view",
        ),
        (
            "Long-Tailed 3D Point Cloud Dataset Distillation",
            "Current point cloud dataset distillation methods ignore the "
            "distributional imbalance prevalent in the source splits.",
            "dataset distillation",
        ),
        (
            "Multimodal Fusion of Visual and Morphometric Features for Bird Bones",
            "We investigate skeletal element identification and family-level "
            "taxonomic classification of avian remains from museum collections.",
            "taxonomic",
        ),
        (
            "FLASH: Efficient Impact Fall Detection with a Hypergraph State-Space Model",
            "Accurate fall detection at the moment an individual hits the ground "
            "is crucial for timely intervention.",
            "fall detection",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords, f"{phrase!r} did not fire on {title!r}"
        assert result.recommended_ring == "Ignore"


def test_v2x_dataset_names_close_the_whole_word_gap(app_config):
    """Anchor: 7747 (HeteroPROMPT) evaded the `v2x` negative added on 07-28. The
    matcher is whole-word, so "V2XSet" and "OPV2V-H" contain no standalone `v2x`
    token; the dataset names are what the abstract actually says."""
    item = make_item(
        "HeteroPROMPT: A Real-time Privacy-Preserving Heterogeneous Collaborative "
        "Perception Framework",
        "Experiments on the OPV2V-H and V2XSet datasets show improved average "
        "precision with orders of magnitude fewer trainable parameters.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "v2xset" in result.negative_keywords
    assert "opv2v" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_image_forensics_paper_does_not_match_robotics_track(app_config):
    """Anchor: 7752 (BG-REAL) reached rank 5 of 2026-07-28 partly because
    `manipulation` matched Robotics Vision on "background manipulation" — the
    third distinct wrong sense of that word after image and world generation."""
    item = make_item(
        "BG-REAL: A Public Real-Data Anchored Benchmark for Background Manipulation "
        "Detection and Localization",
        "Background manipulation is a practical but under-specified image-forensics "
        "setting, where the manipulated evidence can sit outside the salient "
        "foreground object.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Robotics Vision" not in result.tracks


def test_gui_agent_benchmark_does_not_match_tracking_track(app_config):
    """Anchor: 7576 (Desktop-Delta Bench) matched Object Tracking on the bare word
    `tracking`, from "source tracking" of desktop GUI state."""
    item = make_item(
        "Desktop-Delta Bench: Do Computer-Use Models Understand Desktop GUI Transitions?",
        "We probe state verification, source tracking and context-aware control "
        "over multi-app Linux trajectories rendered in a desktop GUI.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Object Tracking" not in result.tracks


def test_medical_anomaly_detection_does_not_match_inspection_track(app_config):
    """Anchor: 7621 matched Industrial Vision Inspection on `anomaly detection`
    alone. That phrase is the track's strongest positive (28 kept items in the
    decided corpus) and medical papers use it for the identical task, so the
    guard is scoped to medical vocabulary rather than weakening the keyword."""
    item = make_item(
        "Group Equivariant Diffusion for Anomaly Detection in Computational Cytology",
        "Anomaly detection frameworks are trained on normal slide-negative "
        "patches of whole-slide images and applied to held-out slides.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "Industrial Vision Inspection" not in result.tracks


def test_industrial_anomaly_detection_still_matches_inspection_track(app_config):
    """Guard on the guard: the medical phrases must not cost a real inspection
    paper its track. 576 (AnomalyClaw, kept) is why `medical imaging` was
    rejected as a guard and only the singular `medical image` is listed."""
    cases = [
        (
            "MMVIAD: A Multi-Modal Industrial Anomaly Detection Benchmark",
            "We release aligned RGB and 3D scans of surface defects from a "
            "production line and benchmark unsupervised anomaly detection.",
        ),
        (
            "AnomalyClaw: A Universal Visual Anomaly Detection Agent",
            "Our tool-grounded agent generalizes across industrial inspection, "
            "remote sensing and medical imaging without retraining.",
        ),
    ]
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert "Industrial Vision Inspection" in result.tracks, title


def test_core_domain_survives_the_2026_07_30_negatives(app_config):
    """Pins the kept-item collisions that forced this round's phrases to stay
    scoped: 6669 (GPS-denied aerial geo-localization, kept Watch) rejected bare
    `satellite` / `geo-localization`, 4395 (HERCULES, kept Evaluate) rejected
    `collaborative perception`, and industrial OCV rejected `ocr`."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "NGPS: GPS-Denied Aerial Geo-Localization and 2.5D Reconstruction",
            "We fuse deep satellite image matching with a multi-rate UKF whose "
            "covariance is modulated by the RANSAC inlier ratio, running in real "
            "time on a Jetson Orin NX.",
        ),
        (
            "HERCULES: An Open-Source Simulation Framework for Multi-Robot SLAM",
            "Our UE5 pipeline supports heterogeneous multi-robot SLAM, "
            "collaborative perception and exploration with released ROS2 code.",
        ),
        (
            "Robust Date-Code Reading on Stamped Metal Parts",
            "We combine a line-scan camera with OCR and optical character "
            "verification to read part markings on an inline inspection cell.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert not result.negative_keywords, (
            f"{title!r} unexpectedly penalised by {result.negative_keywords}"
        )


def test_2026_07_31_negative_topics_fire(app_config):
    """Anchor: the 2026-07-30 queue was an unusually weak day — every one of its
    25 candidates was suggested Ignore, and 12 of the 23 curated Ignore reached
    the top 25 with zero negative penalty. Each fixture pins one class mined out
    of that residue, in the phrasing the real abstracts used."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "RefCaptioner: Multi-Reference Image-Grounded Video Captioning",
            "We require factual video descriptions with phrase-level reference "
            "grounding and evaluate caption factuality on real-world videos.",
            "captioning",
        ),
        (
            "EgoGVAE: Ego-body Mesh Reconstruction via Guided Variational Autoencoder",
            "We recover the full-body mesh from only the head pose, decoding "
            "latent features into natural representations of body poses.",
            "full-body",
        ),
        (
            "4DHumanDiff: Direct Text-to-4DGS Generation for Consistent Humans",
            # Singular by design: the matcher is whole-word, so `dynamic human`
            # does not fire on the bare plural "dynamic humans". 7872 is caught
            # by its other phrasing, "dynamic human assets" — measured as 5
            # Ignore / 0 kept against 1 / 0 for the plural, so the plural is not
            # worth a second list entry.
            "We generate high-quality 360-degree dynamic human assets from text "
            "prompts, represented by 4D Gaussian Splatting.",
            "dynamic human",
        ),
        (
            "ReGenVC: End-to-End Real-Time Generative Video Coding at Ultra-Low Bitrate",
            "The encoder reduces a source clip to a compact bitstream; at a "
            "matched ultra-low bitrate, conventional codecs collapse.",
            "bitrate",
        ),
        (
            "OSReward: Standardized Evaluation for Cross-Platform Reward Models",
            "We benchmark judges of computer-use agent trajectories collected "
            "from diverse agent backbones across platforms.",
            "computer-use",
        ),
        (
            "Beyond Classification: Pathology Foundation Models as Detection Encoders",
            "We ask whether the latent space of current pathology foundation "
            "models is spatially resolved enough for dense object detection.",
            "pathology",
        ),
    ]
    for title, summary, phrase in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert phrase in result.negative_keywords, (
            f"{title!r} matched {result.negative_keywords}, expected {phrase!r}"
        )
        assert result.negative_topic_penalty > 0


def test_pathology_supersedes_computational_pathology(app_config):
    """`computational pathology` was retired in favour of the bare form. The long
    phrase must still be caught, and must be caught exactly ONCE — keeping both
    would have double-counted the penalty on the items that use it."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "CGRL: Context-Guided Representation Learning for WSI Classification",
            "Whole-slide image classification is widely used in computational "
            "pathology because slide-level labels are easier to obtain.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "pathology" in result.negative_keywords
    assert "computational pathology" not in result.negative_keywords


def test_wrong_sense_of_reconstruction_does_not_match_3d_track(app_config):
    """Anchor: bare `reconstruction` is the 3D track's broadest positive and was
    the largest false-context source of the 2026-07-30 queue — five of 25
    candidates matched here on the wrong sense of the word. A track guard is
    worth -12, so it clears a body-only match (+10) outright."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "RefCaptioner: Multi-Reference Image-Grounded Video Captioning",
            "Human evaluation confirms our captions enable more source-faithful "
            "video reconstruction with open-source video generators.",
        ),
        (
            "ACE-Data-0: Human-Centric Ambient Capture as Embodied Data Engine",
            "Our engine records full-body motion and articulated hand motion "
            "with multi-view exocentric video and object geometry.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert "3D Geometry & Reconstruction" not in result.tracks, (
            f"{title!r} still matched the 3D track"
        )


def test_reconstruction_guard_lowers_relevance_when_track_survives(app_config):
    """The guard is a -12 score penalty, not a hard suppression: a title-level
    `reconstruction` match (+20) still clears it. 7861 (EgoGVAE) is that case —
    it keeps the track but loses relevance, which is the whole point of pairing
    the track guard with the global negative. Pins old-vs-new on one item."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    title = "EgoGVAE: Ego-body Mesh Reconstruction via Guided Variational Autoencoder"
    guarded = classify_item(
        make_item(
            title,
            "Benchmark datasets show the method improves full-body ego-body mesh "
            "reconstruction from a single head-joint trajectory.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    control = classify_item(
        make_item(
            title,
            "Benchmark datasets show the method improves ego-body mesh "
            "reconstruction from a single head-joint trajectory.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Geometry & Reconstruction" in guarded.tracks
    assert guarded.relevance_score < control.relevance_score
    assert guarded.final_score < control.final_score


def test_real_3d_reconstruction_still_matches_the_track(app_config):
    """Guard on the guard: the three phrases above must not cost a genuine
    multi-view geometry paper its track."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "Convolutional Neural Shading for High-Quality 3D Reconstruction",
            "We reconstruct high-quality 3D shapes from multi-view images, "
            "capturing variation in dark and textureless regions via a neural "
            "shader and a fine-detail displacement network.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Geometry & Reconstruction" in result.tracks
    assert not result.negative_keywords


def test_radiomics_paper_does_not_match_inspection_track(app_config):
    """Anchor: 7787 matched Industrial Vision Inspection on `quality control`,
    from a "quality-control strategy" for oncology imaging biomarkers."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "Negative controls reveal volume-driven confounding in radiomics",
            "READII-2-ROQC provides a scalable quality control strategy for "
            "developing interpretable imaging biomarkers.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" not in result.tracks


def test_vlm_tool_use_paper_does_not_match_robotics_track(app_config):
    """Anchor: 7807 (FaithEyes) matched Robotics Vision because agentic VLMs call
    "code-based image manipulation" a tool — the fourth wrong sense of the word
    after image generation, world generation and forensics."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "FaithEyes: Towards Faithful Tool Use via Process-Image Verification",
            "Agentic models interleave textual reasoning with explicit tool calls "
            "such as cropping and code-based image manipulation.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Robotics Vision" not in result.tracks


def test_core_domain_survives_the_2026_07_31_negatives(app_config):
    """Pins the kept-item collisions that forced this round's phrases to stay
    scoped: 595/7749 (quantization-aware and TensorRT distillation, kept) rejected
    `distillation`, 4622 (synthetic TEM, kept) rejected `microscopy`, and 1231
    (AV1 motion vectors, kept) rejected bare `codec`."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "Nano-U: Quantization-Aware Distillation for Embedded Segmentation",
            "We combine knowledge distillation and quantization-aware training, "
            "then export the final model through TensorRT for deployment.",
        ),
        (
            "Synthetic Transmission Electron Microscopy for Data-Limited Regimes",
            "We synthesise high-fidelity microscopy images with diffusion "
            "probabilistic models for data-limited materials inspection.",
        ),
        (
            "Motion-Vector-Guided Correspondence from Compressed Video",
            "By leveraging motion vectors inherent to the AV1 video codec we "
            "bypass computationally expensive exhaustive matching.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert not result.negative_keywords, (
            f"{title!r} unexpectedly penalised by {result.negative_keywords}"
        )


def test_mllm_leaderboard_paper_gets_closed_source_penalty(app_config):
    """Anchor: 7956 (CAER) and the wider MLLM-eval class report results against
    "N open-source and M closed-source models". `closed-source` is the
    highest-yield clean phrase left in the corpus at 31 Ignore / 0 kept."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "AgroTools: A Benchmark for Tool-Augmented Multimodal Agents",
            "We benchmark 9 open-source and 4 closed-source models on outcome-level "
            "task success across a suite of held-out scenarios.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "closed-source" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_unified_multimodal_generation_gets_visual_generation_penalty(app_config):
    """Anchor: 7890 carried zero penalty because unified-multimodal papers say
    "visual generation" where `image generation` / `video generation` expect the
    modality to be named."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "Scaling Properties of Text Conditioning in Visual Generation",
            "The converged diffusion loss scales with the amount of structured "
            "language in the prompt, which lets us improve diffusability.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "visual generation" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_retinal_oct_paper_loses_inspection_relevance(app_config):
    """Anchor: 7949 (ReMoE) matched Industrial Vision Inspection purely on
    `anomaly detection` in a retinal OCT/OCTA paper — the same shape as the
    `quality control` / radiomics case, on the track's other core positive.

    The guard does not strip the track here: `anomaly detection` sits in the
    title, so it out-scores the -12 guard. What it does remove is the relevance
    boost, which is the half that decides queue rank. Pinned as a delta against
    the identical abstract with the medical modality named differently.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    title = "ReMoE: Report-Guided Mixture-of-Experts for Multimodal Anomaly Detection"
    guarded = classify_item(
        make_item(
            title,
            "In retinal optical coherence tomography anomaly detection, existing "
            "unsupervised methods rely on reconstruction residuals.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    unguarded = classify_item(
        make_item(
            title,
            "In retinal scan anomaly detection, existing unsupervised methods "
            "rely on reconstruction residuals.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in guarded.tracks
    assert guarded.relevance_score < unguarded.relevance_score


def test_rgbd_saliency_benchmark_does_not_match_3d_sensors_track(app_config):
    """Anchor: 7929 (SaliLLM) matched 3D Sensors on `rgb-d`, which RGB-D salient
    object detection reuses verbatim from the depth-sensor vocabulary."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "Is It Time for the Renaissance of Salient Object Detection?",
            "We re-engineer RGB-D datasets with phrases, boxes and attributes to "
            "establish a diagnostic benchmark for salient object detection.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Sensors" not in result.tracks


def test_core_domain_survives_the_2026_08_03_negatives(app_config):
    """Pins the kept-item collisions that this round's rejected phrases would
    have caused: 7917 (ZSAD across industrial *and medical* benchmarks, kept
    Evaluate) rejected `medical`, 2153 (real-to-twin inspection, kept) rejected
    bare `avatar`, 7514 (ISP pipeline evaluation, kept) rejected `image quality
    assessment`, and 989 (LiDAR domain shift, sensor work) rejected `weather`.
    A genuine LiDAR geometry paper must also keep its 3D Sensors track."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    cases = [
        (
            "VFAD: Frequency-Adaptive Representation Learning for Zero-Shot Anomaly Detection",
            "Extensive experiments on 13 industrial and medical benchmarks show "
            "improved defect localisation on unseen categories.",
        ),
        (
            "Active Real-to-Twin Inspection: Zero-Shot Anomaly Detection on Assemblies",
            "A digital twin avatar of the part drives next-best-view capture for "
            "industrial surface inspection.",
        ),
        (
            "A Reference-Free Framework for Evaluating Single-Frame ISP Pipelines",
            "We perform no-reference image quality assessment of raw-to-sRGB "
            "camera pipelines under controlled illumination.",
        ),
    ]
    for title, summary in cases:
        result = classify_item(
            make_item(title, summary), config=app_config, source=source, now=FIXTURE_NOW
        )
        assert not result.negative_keywords, (
            f"{title!r} unexpectedly penalised by {result.negative_keywords}"
        )

    lidar = classify_item(
        make_item(
            "CorrelationFlow: A Training-Free Geometric Approach for LiDAR Scene Flow",
            "Connected-component labeling and correlation maximization on "
            "bird's-eye-view occupancy images recover per-object motion under "
            "adverse weather and long range.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Sensors" in lidar.tracks
    assert not lidar.negative_keywords


def test_agentic_tool_calling_paper_gets_tool_use_penalty(app_config):
    """Anchor: 8025 (VC-Tooler) reached the queue on `open source` alone.
    `tool use` is 16 Ignore / 0 kept; bare `agentic` was rejected at 28/7."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "VC-Tooler: Learning Compositional and Adaptive Visual Tool Use",
            "Effective visual tool use requires grounding tool calls in visual "
            "context and composing tools across multiple steps. We release an "
            "open source trajectory bank.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "tool use" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_industrial_anomaly_agent_keeps_its_tool_grounded_wording(app_config):
    """The counterpart to the test above. `agentic` was rejected because it hits
    576 (AnomalyClaw), 1832 (IndusAgent) and 6730 (O-VAD), all kept. Those items
    say "tool-grounded"/"agent" and never "tool use" — that difference is the
    whole reason the narrow phrase is safe, so it is pinned."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "IndusAgent: Reinforcing Open-Vocabulary Industrial Anomaly Detection",
            "An agentic system grounds its reasoning in calibrated inspection "
            "tools to localise surface defects on production parts.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert not result.negative_keywords, (
        f"industrial agent unexpectedly penalised by {result.negative_keywords}"
    )


def test_audiovisual_response_dataset_gets_penalty(app_config):
    """Anchor: 8176 (InteracVid) carried zero penalty. `audio-visual` is the
    round's highest fresh yield at 13 Ignore / 0 kept, 11 of them unpenalised."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "InteracVid: Building a Real Interactive Audio-Visual Response Dataset",
            "Every sample couples a preceding audio-visual context and an "
            "external stimulus with the real interactive response that follows.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "audio-visual" in result.negative_keywords
    assert result.negative_topic_penalty > 0


def test_event_action_benchmark_loses_the_3d_geometry_track(app_config):
    """Anchor: 8073 (Event ActivityNet) reached the 3D Geometry & Reconstruction
    track purely on "action-center reconstruction LPIPS" — a diagnostic metric
    inside a video action-localization benchmark. `action recognition` is 4/0
    in-track and also a global negative, so the item loses the track *and* the
    relevance boost, not only the penalty."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "Event ActivityNet: A Large-Scale Simulated-Event Benchmark",
            "We use action-center reconstruction LPIPS as a soft diagnostic and "
            "establish baselines for annotated-segment action recognition.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Geometry & Reconstruction" not in result.tracks
    assert "action recognition" in result.negative_keywords


def test_xai_acronym_penalised_but_interpretability_claims_are_not(app_config):
    """Anchor: 8006 and 8138 are XAI/attribution papers. Only the acronym is safe:
    `interpretability` (24/1), `explainable` (12/1) and `grad-cam` (2/2) all hit
    kept items, because interpretability is a property the radar's own items
    claim. Pinned as a pair so a later broadening is caught."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    xai = classify_item(
        make_item(
            "A Controlled Benchmark of Attribution Methods on Vision Transformers",
            "Most evidence on the effectiveness of XAI attribution methods has "
            "been established on convolutional networks.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "xai" in xai.negative_keywords

    kept = classify_item(
        make_item(
            "Same Predictions, Different Reasons: The Effect of Quantization",
            "We use Grad-CAM to show that post-training quantization preserves "
            "accuracy while shifting the interpretability of edge deployments.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert not kept.negative_keywords, (
        f"quantization study unexpectedly penalised by {kept.negative_keywords}"
    )


def test_novel_view_synthesis_noise_is_knowingly_uncovered(app_config):
    """Documents the round's largest *unfixed* noise class. Seven of the 40
    Ignores were pure novel-view-synthesis papers reaching 3D Geometry on bare
    `reconstruction` / `multi-view`. Every discriminating phrase collides with
    kept items (`gaussian splatting` 48/22, `novel view synthesis` 21/9, `psnr`
    16/2), because kept geometry work uses the same rendering vocabulary.

    This test asserts the *current, deliberate* behaviour: the NVS paper still
    enters the track with no penalty. If someone later adds a splatting negative,
    this fails and sends them to the comment in topics.yaml explaining why the
    class needs the scoring re-weight instead.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    nvs = classify_item(
        make_item(
            "UniqueSplat: View-conditioned Gaussian Splatting for Generalizable 3D Reconstruction",
            "We propose a view-conditioned feed-forward 3D Gaussian Splatting "
            "model that adapts Gaussians to each view query, improving PSNR on "
            "novel view synthesis benchmarks.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Geometry & Reconstruction" in nvs.tracks
    assert not nvs.negative_keywords

    geometry = classify_item(
        make_item(
            "GLAM-SLAM: Real-time Gaussian Large-scale Mapping via Flow Densification",
            "Gaussian splatting is coupled to LiDAR odometry and bundle "
            "adjustment for drift-robust large-scale dense reconstruction, "
            "evaluated by PSNR and by trajectory error.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Geometry & Reconstruction" in geometry.tracks
    assert not geometry.negative_keywords


def test_extrinsic_rotation_calibration_reaches_the_calibration_track(app_config):
    """Anchor: 8262 (PLS-Calib) scored 21.9 and matched only 3D Sensors, on
    `event camera` — the Calibration & Camera Models track never fired despite an
    abstract centred on extrinsic calibration. Whole-word matching is the cause:
    "extrinsic *rotation* calibration" is not the phrase `extrinsic calibration`,
    and "circular calibration *targets*" is not `calibration target`.

    Pins both halves of the 2026-08-05 fix — the added phrase and the plural.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(
        make_item(
            "PLS-Calib: A Partial Least Squares Framework for Event Camera and "
            "Odometry Calibration under Ground Motion Constraints",
            "Accurate extrinsic rotation calibration between sensors is fundamental "
            "to robotic perception. We introduce a polarity-aware event "
            "representation which enhances spatiotemporal contrast in circular "
            "calibration targets, improving calibration accuracy over "
            "state-of-the-art methods.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Calibration & Camera Models" in result.tracks
    assert "Target Detection & Fiducials" in result.tracks
    assert "rotation calibration" in result.positive_keywords
    assert "calibration targets" in result.positive_keywords


def test_time_series_anomaly_detection_is_docked_on_the_inspection_track(app_config):
    """Anchor: 8191 (PRISM) matched Industrial Vision Inspection on the bare
    phrase `anomaly detection` while being a *time-series* AD paper for finance
    and cloud computing.

    Pins what the guard actually does, which is worth being precise about: it
    subtracts a flat 12 from the track score, so a *title* match (+18) survives
    at 6 and only a body-only match (+10) is stripped outright. PRISM says
    "Anomaly Detection" in its title, so it keeps the track but loses two thirds
    of its relevance — enough to move it 27.7 -> 22.0 overall. Anyone later
    surprised that the track is still listed should read this rather than
    reach for a bigger hammer.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    tsad = classify_item(
        make_item(
            "PRISM: Time Series to Image Representations for Multivariate Anomaly Detection",
            "Time series anomaly detection underpins applications in predictive "
            "maintenance, finance, and cloud computing. We map multivariate series "
            "to multi-channel images and reuse ImageNet-pretrained encoders.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert tsad.relevance_score == 6.0

    body_only = classify_item(
        make_item(
            "PRISM: Representations for Multivariate Sensor Streams",
            "Time series anomaly detection underpins predictive maintenance, "
            "finance, and cloud computing workloads.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" not in body_only.tracks

    inspection = classify_item(
        make_item(
            "Surface Inspection of Rolled Steel with Learned Defect Detection",
            "Our machine vision system performs visual inspection and defect "
            "detection on the production line, with anomaly detection thresholds "
            "tuned per batch.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in inspection.tracks
    assert inspection.relevance_score > tsad.relevance_score


def test_quantization_and_ptq_noise_stays_off_geometry_and_edge_tracks(app_config):
    """Anchors 8193 (low-bit PTQ, where "reconstruction" means re-fitting a
    quantized layer) and 8303 (bit-serial schedule for diffusion denoising steps).
    Both matched tracks on the wrong sense of a strong positive. The kept half
    pins that ordinary edge-deployment quantization work is untouched."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    ptq = classify_item(
        make_item(
            "Low-Dimensional Subspace Optimization for Neural Network Quantization",
            "Low-bit quantization suffers accuracy degradation on compact networks. "
            "PTQ reconstructs fixed pretrained models without improving inherent "
            "quantization friendliness, evaluated on ImageNet and CIFAR-100.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "3D Geometry & Reconstruction" not in ptq.tracks

    diffusion = classify_item(
        make_item(
            "TASQ: Temporal-Adaptive Bit Sparsification Quantization for Diffusion Models",
            "Static quantization assigns one weight precision to every denoising "
            "step. A Temporal-Precision Engine maps the learned schedule to "
            "bit-serial execution, reducing execution cycles on SDXL-Turbo.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Edge AI & Deployment" not in diffusion.tracks

    kept = classify_item(
        make_item(
            "INT8 Quantization for Real-Time Defect Detection on Embedded Vision",
            "We export the detector to ONNX and TensorRT, apply quantization and "
            "pruning, and measure real-time inference latency on the edge device.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Edge AI & Deployment" in kept.tracks


def test_medical_image_subsumes_the_two_longer_medical_phrases(app_config):
    """`medical image segmentation` and `medical image analysis` were folded into
    the bare `medical image` on 2026-08-05: it strictly subsumes both under
    whole-word matching and stops them stacking a redundant +10. 8261 (imbalanced
    medical image *classification*) is the form neither longer phrase caught.

    The negative half pins the deliberate boundary: `medical imaging` is a
    separate entry because "image" does not match "imaging", and bare `medical`
    stays unused so kept items that merely name medicine as one application
    domain are not penalised.
    """
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    for phrase in (
        "medical image segmentation is dominated by U-Net variants",
        "we advance medical image analysis with foundation models",
        "recurrent contrastive learning for imbalanced medical image classification",
    ):
        result = classify_item(
            make_item("Medical Study", phrase),
            config=app_config,
            source=source,
            now=FIXTURE_NOW,
        )
        assert "medical image" in result.negative_keywords, phrase

    biomedical = classify_item(
        make_item(
            "AnomalyClaw: A General Visual Anomaly Detection Agent",
            "The agent generalises across industrial surface inspection, "
            "biomedical screening and remote inspection domains.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "medical image" not in biomedical.negative_keywords


def test_multi_person_penalised_but_motion_prediction_in_tracking_is_not(app_config):
    """`multi-person` (7/0) extends the `human <x>` family to the multi-subject
    form; bare `motion prediction` was REJECTED (2/2) because predicting motion is
    what a tracker does. Pinned as a pair so a later broadening is caught."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    human = classify_item(
        make_item(
            "Residual Flow Matching for 3D Multi-Person Motion Prediction",
            "3D multi-person motion prediction requires modeling both individual "
            "kinematics and inter-person interactions over skeletal sequences.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "multi-person" in human.negative_keywords

    tracker = classify_item(
        make_item(
            "SAMOFT: Robust Multi-Object Tracking via Region and Motion Prediction",
            "Our tracker couples data association with motion prediction to keep "
            "identities stable through occlusion in multi-object tracking.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert not tracker.negative_keywords, (
        f"MOT tracker unexpectedly penalised by {tracker.negative_keywords}"
    )


def test_scene_text_penalised_but_industrial_ocr_is_not(app_config):
    """`scene text` (7/0) targets in-the-wild street-sign recognition. Bare `ocr`
    stays deliberately out of negative_topics.yaml — industrial character
    verification is the radar's own domain and says "OCR" verbatim."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    scene = classify_item(
        make_item(
            "Out-of-Length Scene Text Recognition: A Two-Axis Diagnosis",
            "In-the-wild scene text recognition degrades on long words; we "
            "diagnose the failure and propose a training-free fix.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "scene text" in scene.negative_keywords

    industrial = classify_item(
        make_item(
            "OCR-Based Date-Code Verification on the Packaging Line",
            "An industrial inspection system reads laser-etched date codes with "
            "OCR and flags misprints during quality control.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert not industrial.negative_keywords, (
        f"industrial OCR unexpectedly penalised by {industrial.negative_keywords}"
    )


def test_ultrasound_guard_strips_inspection_track_but_ultrasonic_ndt_keeps_it(app_config):
    """8365 (FUSEP, fetal ultrasound) reached Industrial Vision Inspection on
    `quality control`. The guard is safe only because the two senses use
    different words: medical says "ultrasound", industrial NDT says "ultrasonic".
    Track guards bypass the `exemptions:` map in negative_topics.yaml, so this
    pair is pinned to catch a later broadening."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    medical = classify_item(
        make_item(
            "FUSEP: A Benchmark for Early Pregnancy Fetal Ultrasound Screening",
            "We report quality control on ultrasound images across three hospitals "
            "with box-level expert annotations for screening.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" not in medical.tracks

    ndt = classify_item(
        make_item(
            "Ultrasonic Weld Inspection with Learned Defect Detection",
            "Non-destructive ultrasonic testing of welds supports automated defect "
            "detection and quality control on the production line.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in ndt.tracks


def test_surveillance_footage_guard_but_industrial_vad_keeps_track(app_config):
    """8337 (VQ-VAD) reached Industrial Vision Inspection on `anomaly detection`
    from surveillance footage. Bare `surveillance` and `video anomaly detection`
    were both REJECTED as guards: they hit kept items 24 (SphereVAD) and 6730
    (O-VAD, *industrial* video anomaly detection).

    The guard subtracts from the track score rather than always stripping the
    track: 8337 says "Anomaly Detection" in its *title* (+18), so it keeps the
    track at reduced weight. Asserting the reduction rather than removal is what
    the guard actually promises."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    title = "VQ-VAD: Vector-Quantized Motion Representation for Video Anomaly Detection"
    surveillance = classify_item(
        make_item(
            title,
            "Pose-based anomaly detection mitigates the visual variability of "
            "surveillance footage, including changes in lighting and viewpoint.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    neutral = classify_item(
        make_item(
            title,
            "Pose-based anomaly detection mitigates the visual variability of "
            "recorded scenes, including changes in lighting and viewpoint.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert surveillance.relevance_score < neutral.relevance_score

    industrial = classify_item(
        make_item(
            "O-VAD: Industrial Video Anomaly Detection through Object-Centric Tracking",
            "We detect process anomalies on the line by combining video anomaly "
            "detection with object-centric tracking for visual inspection.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in industrial.tracks
    assert not industrial.negative_keywords


def test_eda_routing_guard_but_pcb_inspection_keeps_its_tracks(app_config):
    """8419 (OmniRouting) reached Robot Guidance + Robotics Vision on the EDA
    sense of `path planning` / `navigation`. `pcb` and `printed circuit board`
    were REJECTED as guards — both hit kept items, because board *inspection* is
    the radar's own domain."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    eda = classify_item(
        make_item(
            "OmniRouting: A Multimodal Benchmark for Constraint-Aware PCB Routing",
            "Routing is a critical stage of electronic design automation; we test "
            "path planning and navigation over netlists under design-rule constraints.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Robot Guidance" not in eda.tracks
    assert "Robotics Vision" not in eda.tracks

    inspection = classify_item(
        make_item(
            "Masked Pretraining for PCB Defect Detection",
            "Surface inspection of printed circuit board assemblies with defect "
            "detection under industrial inspection conditions.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Industrial Vision Inspection" in inspection.tracks


def test_video_clip_guard_but_clip_foundation_model_keeps_vfm_track(app_config):
    """8393 (EgoCross) reached Vision Foundation Models on `clip` from "egocentric
    video clip". `clip-level` was REJECTED earlier at 7/1; the two-word `video
    clip` never fires on the model name."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    generic = classify_item(
        make_item(
            "The First EgoCross Challenge: Cross-Domain Egocentric Video QA",
            "Each test example consists of an egocentric video clip, a question, "
            "and four candidate answers.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Vision Foundation Models" not in generic.tracks

    model = classify_item(
        make_item(
            "Probing CLIP and DINOv2 Features for Dense Correspondence",
            "We compare frozen CLIP and DINOv2 backbones as a vision foundation "
            "model for dense matching.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "Vision Foundation Models" in model.tracks


def test_video_language_and_long_form_video_penalised_but_tracking_is_not(app_config):
    """`vision-language` has been a negative since 2026-05-11 but never fires on
    the Video-LLM genre, which writes "Video-Language". Pinned with a video
    tracking item to catch a broadening that would swallow legitimate video work."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    video_llm = classify_item(
        make_item(
            "CLIP-CC-Bench: Paragraph-Level Video Descriptions in Video-Language Models",
            "An evaluation suite for long-form video description built from movie "
            "content segmented into 90-second segments.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "video-language" in video_llm.negative_keywords
    assert "long-form video" in video_llm.negative_keywords

    tracker = classify_item(
        make_item(
            "Long-Horizon Multi-Object Tracking in Industrial Video",
            "Temporal association keeps identities stable across occlusion on the "
            "conveyor, using a motion model for object tracking.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert not tracker.negative_keywords, (
        f"video tracker unexpectedly penalised by {tracker.negative_keywords}"
    )


def test_railway_penalised_but_industrial_inspection_is_not(app_config):
    """Rail perception is a small off-domain cluster that took 2 of 25 slots on
    2026-08-05. Bare `rail` was deliberately not used — it risks firing on "guard
    rail" and similar."""
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    rail = classify_item(
        make_item(
            "A Multi-Sensor Dataset for Monitoring Rail Vehicle Environments",
            "A multi-sensor dataset tailored to railway environment perception "
            "with 7 million annotations for automated train operation.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert "railway" in rail.negative_keywords

    industrial = classify_item(
        make_item(
            "Guard Rail Weld Seam Surface Inspection",
            "Automated surface inspection of weld seams uses defect detection "
            "during industrial inspection and quality control.",
        ),
        config=app_config,
        source=source,
        now=FIXTURE_NOW,
    )
    assert not industrial.negative_keywords, (
        f"industrial inspection unexpectedly penalised by {industrial.negative_keywords}"
    )


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


def test_medical_modality_tail_second_wave_gets_negative_penalty(app_config):
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
