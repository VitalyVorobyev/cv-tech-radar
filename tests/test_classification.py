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
    do not demote the legitimate Industrial Vision Inspection track match or
    push final_score below the Watch threshold.
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
    assert result.final_score >= app_config.scoring.thresholds.watch
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
    "medical image segmentation". The `medical image segmentation` negative
    fires on the task and keeps the recommended ring at Ignore.
    """
    item = make_item(
        "HPR-SAM: Prompt-free SAM for Medical Image Segmentation",
        "We adapt the Segment Anything Model (SAM) for automatic medical image "
        "segmentation of anatomical structures, evaluated on public benchmarks. "
        "Code is available at https://github.com/example/hpr-sam.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source, now=FIXTURE_NOW)
    assert "medical image segmentation" in result.negative_keywords
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
    assert "computed tomography" in result.negative_keywords
    assert "clinical" in result.negative_keywords
    assert result.recommended_ring == "Ignore"


def test_human_pose_estimation_papers_get_negative_penalty(app_config):
    """Anchor: 2026-07-10 daily run candidate 6284 (TSR-Ego).

    TSR-Ego is an egocentric 3D human pose estimation paper that reached the
    top-25 with a *zero* negative penalty — it matched the Calibration & Camera
    Models + 3D Geometry tracks via `fisheye` / `stereo` / `pose estimation`.
    Human-body CV (HPE) is outside the industrial-CV radar; the `human pose`
    and `egocentric` negatives fire on the task and drop the ring to Ignore
    without touching the `pose estimation` positive (a camera-pose paper never
    says "human pose").
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
    assert "human pose" in result.negative_keywords
    assert "egocentric" in result.negative_keywords
    assert result.negative_topic_penalty > 0
    assert result.recommended_ring == "Ignore"


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
            "gaze",
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
        (
            "OffNadirLoc: UAV-to-Satellite Geo-Localization under Large Off-Nadir Views",
            "Cross-view localization between drone and satellite imagery remains "
            "challenging. We release a benchmark on github.",
            "satellite imagery",
        ),
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
            "medical image analysis",
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
