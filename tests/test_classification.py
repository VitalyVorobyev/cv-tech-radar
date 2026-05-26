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
