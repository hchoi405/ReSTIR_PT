/***************************************************************************
 # Copyright (c) 2015-21, NVIDIA CORPORATION. All rights reserved.
 #
 # NVIDIA CORPORATION and its licensors retain all intellectual property
 # and proprietary rights in and to this software, related documentation
 # and any modifications thereto.  Any use, reproduction, disclosure or
 # distribution of this software and related documentation without an express
 # license agreement from NVIDIA CORPORATION is strictly prohibited.
 **************************************************************************/
import Utils.Attributes;
import Utils.Sampling.TinyUniformSampleGenerator;
import Utils.Debug.PixelDebug;
import SurfaceData;
import EvalContext;
import Lights;
import Resampling;
import Params;

/** Performs temporal resampling by combining the reservoir from the initial
    resampling pass with a reservoir from the last frame obtained through
    reprojection.
*/
struct TemporalResampling
{
    // Static configuration.
    static const uint kMaxHistoryLength = MAX_HISTORY_LENGTH;

    static const bool kUsePairwiseMIS = USE_PAIRWISE_MIS;
    static const bool kUnbiased = UNBIASED;

    static const DebugOutput kDebugOutput = DebugOutput(DEBUG_OUTPUT);

    [root] StructuredBuffer<PackedSurfaceData> surfaceData;
    [root] StructuredBuffer<PackedSurfaceData> prevSurfaceData;
    Texture2D<float2> motionVectors;
    RWStructuredBuffer<PackedReservoir> reservoirs;
    StructuredBuffer<PackedReservoir> prevReservoirs;
    RWStructuredBuffer<PackedReservoir> reservoirs2;
    StructuredBuffer<PackedReservoir> prevReservoirs2;
    RWTexture2D<float4> debugOutput;
    RWTexture2D<float4> temporalLi;

    Lights lights;

    uint2 frameDim;
    uint frameIndex;

    float normalThreshold;
    float depthThreshold;

    bool fixSpatialSeed;
    uint spatialSeed;
    bool fixTemporalSeed;
    uint temporalSeed;
    uint temporalSeedOffset;

    uint gTileWidth;
    bool useTileSeed;

    uint getPixelIndex(uint2 pixel) { return pixel.y * frameDim.x + pixel.x; }

    bool isValidPixel(int2 pixel) { return all(pixel >= 0 && pixel < frameDim); }

    void process(uint2 pixel)
    {
        if (any(pixel >= frameDim)) return;

        printSetPixel(pixel);

        if (kDebugOutput == DebugOutput::TemporalReuse) debugOutput[pixel] = float4(1.f, 0.f, 0.f, 0.f);

        const uint pixelIndex = getPixelIndex(pixel);

        uint2 tileSeed = pixel % gTileWidth;

        uint2 spatialSeed2 = fixSpatialSeed ? spatialSeed : (useTileSeed ? tileSeed : pixel);
        uint temporalSeed2 = fixTemporalSeed ? temporalSeed : frameIndex;

        // Setup evaluation context for current pixel.
        const EvalContext currentContext = EvalContext::create(pixel, frameDim, SurfaceData::createFromPacked(surfaceData[pixelIndex]));
        if (!currentContext.isValid()) return;
        const Reservoir currentReservoir = Reservoir::createFromPacked(reservoirs[pixelIndex]);

        {
            var sg = TinyUniformSampleGenerator(spatialSeed2, temporalSeedOffset + temporalSeed2);

            // Back-project this pixel to previous frame.
            const int2 prevPixel = pixel + motionVectors[pixel] * frameDim + (sampleNext2D(sg) * 1.f - 0.f);
            if (!isValidPixel(prevPixel)) return;
            const uint prevPixelIndex = getPixelIndex(prevPixel);

            // Setup evaluation context for back-projected pixel.
            const EvalContext prevContext = EvalContext::create(prevPixel, frameDim, SurfaceData::createFromPacked(prevSurfaceData[prevPixelIndex]));
            if (!prevContext.isValid()) return;

            // Write debug output.
            if (kDebugOutput == DebugOutput::TemporalReuse) debugOutput[pixel] = float4(0.f, 1.f, 0.f, 0.f);

            {
                // Load reservoirs.
                Reservoir prevReservoir = Reservoir::createFromPacked(prevReservoirs[prevPixelIndex]);
                prevReservoir.M = min(prevReservoir.M, currentReservoir.M * kMaxHistoryLength);

                // Setup resampling.
                RisState risState = RisState::createEmpty();

                if (kUsePairwiseMIS)
                {
                    const LoadedLightSample currentLightSample = lights.loadLightSample(currentReservoir.lightSample);
                    float currentTargetPdf = currentContext.evalTargetFunction(currentLightSample);
                    streamingResampleStepMis(risState, currentReservoir, currentLightSample, currentTargetPdf, currentContext, prevReservoir, prevContext, 1, lights, sg);
                    streamingResampleFinalizeMis(risState, currentReservoir, currentTargetPdf, sg);
                    risState.weight = risState.weight > 0.f ? risState.weightSum / risState.weight : 0.f;
                }
                else
                {
                    // Check if previous sample is valid for reuse.
                    if (!kUnbiased && !currentContext.isValidNeighbor(prevContext, normalThreshold, depthThreshold)) return;

                    // Resample current and previous reservoirs.
                    streamingResampleStep(risState, currentReservoir, currentContext, lights, sg);
                    bool usedPrev = streamingResampleStep(risState, prevReservoir, currentContext, lights, sg);

                    // Compute the unbiased normalization term (instead of using 1/M).
                    const LoadedLightSample lightSample = lights.loadLightSample(risState.lightSample);
                    float currentPdf = currentContext.evalTargetFunction(lightSample, kUnbiased);
                    float prevPdf = prevContext.evalTargetFunction(lightSample, kUnbiased);
                    float normalization = (usedPrev ? prevPdf : currentPdf) / (currentReservoir.M * currentPdf + prevReservoir.M * prevPdf);
                    risState.weight = risState.weight > 0.f ? (risState.weightSum * normalization) / risState.weight : 0.f;
                }

                // Save reservoir.
                reservoirs[pixelIndex] = risState.toReservoir().pack();
            }

            // Dual buffer
            {
                // Load reservoirs.
                Reservoir prevReservoir2 = Reservoir::createFromPacked(prevReservoirs2[prevPixelIndex]);
                prevReservoir2.M = min(prevReservoir2.M, currentReservoir.M * kMaxHistoryLength);

                // Setup resampling.
                RisState risState2 = RisState::createEmpty();

                if (kUsePairwiseMIS)
                {
                    const LoadedLightSample currentLightSample = lights.loadLightSample(currentReservoir.lightSample);
                    float currentTargetPdf = currentContext.evalTargetFunction(currentLightSample);
                    streamingResampleStepMis(risState2, currentReservoir, currentLightSample, currentTargetPdf, currentContext, prevReservoir2, prevContext, 1, lights, sg);
                    streamingResampleFinalizeMis(risState2, currentReservoir, currentTargetPdf, sg);
                    risState2.weight = risState2.weight > 0.f ? risState2.weightSum / risState2.weight : 0.f;
                }
                else
                {
                    // Check if previous sample is valid for reuse.
                    if (!kUnbiased && !currentContext.isValidNeighbor(prevContext, normalThreshold, depthThreshold)) return;

                    // Resample current and previous reservoirs.
                    streamingResampleStep(risState2, currentReservoir, currentContext, lights, sg);
                    bool usedPrev = streamingResampleStep(risState2, prevReservoir2, currentContext, lights, sg);

                    // Compute the unbiased normalization term (instead of using 1/M).
                    const LoadedLightSample lightSample = lights.loadLightSample(risState2.lightSample);
                    float currentPdf = currentContext.evalTargetFunction(lightSample, kUnbiased);
                    float prevPdf = prevContext.evalTargetFunction(lightSample, kUnbiased);
                    float normalization = (usedPrev ? prevPdf : currentPdf) / (currentReservoir.M * currentPdf + prevReservoir2.M * prevPdf);
                    risState2.weight = risState2.weight > 0.f ? (risState2.weightSum * normalization) / risState2.weight : 0.f;
                }

                // Save reservoir.
                reservoirs2[pixelIndex] = risState2.toReservoir().pack();
            }

            // History (w/o current sample)
            {
                // Load reservoirs.
                Reservoir prevReservoir2 = Reservoir::createFromPacked(prevReservoirs2[prevPixelIndex]);

                // Setup resampling.
                RisState risState2 = RisState::createEmpty();

                // Constant MIS
                {
                    // Check if previous sample is valid for reuse.
                    if (!kUnbiased && !currentContext.isValidNeighbor(prevContext, normalThreshold, depthThreshold)) return;

                    // Resample current and previous reservoirs.
                    bool usedPrev = streamingResampleStep(risState2, prevReservoir2, currentContext, lights, sg);

                    // Compute the unbiased normalization term (instead of using 1/M).
                    const LoadedLightSample lightSample = lights.loadLightSample(risState2.lightSample);
                    float prevPdf = prevContext.evalTargetFunction(lightSample, kUnbiased);
                    float normalization = (usedPrev ? prevPdf : 0.f) / (prevReservoir2.M * prevPdf);
                    risState2.weight = risState2.weight > 0.f ? (risState2.weightSum * normalization) / risState2.weight : 0.f;
                }

                float3 Li = float3(0.f);
                var reservoir = risState2.toReservoir();
                if (reservoir.isValid())
                {
                    // Evaluate light sample.
                    EvaluatedLightSample evaluatedLightSample = lights.evalLightSample(reservoir.lightSample, currentContext.pos);
                    // Evaluate visibility.
                    float visibility = currentContext.evalVisibility(evaluatedLightSample);
                    if (visibility > 0.f)
                    {
                        if (evaluatedLightSample.distance > 0.f)
                        {
                            Li = reservoir.weight * evaluatedLightSample.geomFactor * lights.evalEmission(reservoir.lightSample);
                        }
                    }
                }
                temporalLi[pixel] = float4(Li, 1.f);
            }
        }
    }
};

cbuffer CB
{
    TemporalResampling gTemporalResampling;
}

[numthreads(16, 4, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    gTemporalResampling.process(dispatchThreadId.xy);
}
