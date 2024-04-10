/***************************************************************************
 # Copyright (c) 2022, Daqi Lin.  All rights reserved.
 **************************************************************************/
import Params;
import Shift;
import Scene.HitInfo;
import PathReservoir;
import PathTracer;
import Scene.Scene;
import Utils.Debug.PixelDebug;
import Rendering.Utils.PixelStats;
import Utils.Sampling.TinyUniformSampleGenerator;
import Utils.Math.Ray;
import LoadShadingData;
import Rendering.Materials.MaterialShading;

/** TODO.
*/
struct PathRetracePass
{
    static const uint kNeighborOffsetCount = NEIGHBOR_OFFSET_COUNT;
    static const uint kNeighborOffsetMask = kNeighborOffsetCount - 1;

    // Resources
    RestirPathTracerParams params;                        ///< Runtime parameters.

    Texture2D<PackedHitInfo> vbuffer;                     ///< Fullscreen V-buffer for the primary hits.
    Texture2D<PackedHitInfo> temporalVbuffer;
    Texture2D<float2> motionVectors;

    ByteAddressBuffer nRooksPattern;

    RWTexture2D<float4> outputColor;                      ///< Output resolved color.
    RWStructuredBuffer<PathReservoir> outputReservoirs;
    RWStructuredBuffer<PathReservoir> temporalReservoirs;
    RWStructuredBuffer<PixelReconnectionData> reconnectionDataBuffer;

    int  gNumSpatialRounds;
    bool gEnableTemporalReprojection;

    float gTemporalHistoryLength;
    bool gNoResamplingForTemporalReuse;

    bool fixSpatialSeed;
    uint spatialSeed;
    bool fixTemporalSeed;
    uint temporalSeed;
    uint temporalSeedOffset;

    uint gTileWidth;
    bool useTileSeed;

    bool isValidPackedHitInfo(PackedHitInfo packed)
    {
        return packed.x != 0;
    }

    bool isValidScreenRegion(int2 pixel) { return all(pixel >= 0 && pixel < params.frameDim); }

    ShadingData getPixelShadingData(int2 pixel, out PackedHitInfo PrimaryHitPacked)
    {
        ShadingData sd = {};
        Ray ray = gScene.camera.computeRayPinhole(pixel, params.frameDim);
        PrimaryHitPacked = vbuffer[pixel];
        if (isValidPackedHitInfo(PrimaryHitPacked))
        {
            HitInfo PrimaryHit; PrimaryHit.unpack(PrimaryHitPacked);
            sd = loadShadingData(PrimaryHit, -ray.dir, true);
        }
        return sd;
    }

    ShadingData getPixelTemporalShadingData(int2 pixel, out PackedHitInfo PrimaryHitPacked)
    {
        ShadingData sd = {};
        Ray ray = gScene.camera.computeRayPinholePrevFrame(pixel, params.frameDim);
        PrimaryHitPacked = temporalVbuffer[pixel];
        if (isValidPackedHitInfo(PrimaryHitPacked))
        {
            HitInfo PrimaryHit; PrimaryHit.unpack(PrimaryHitPacked);
            sd = loadShadingData(PrimaryHit, -ray.dir, true);
        }
        return sd;
    }

    /*
    * Build a reservoir of paths whose suffix can be merged to a pixel's prefix.
    * This method is optimized for small windows such that we can run the entire
    * algorithm in one pass.
    */
    void ReSTIR(const uint2 pixel)
    {
        uint2 tileSeed = pixel % gTileWidth;

        // TODO: How to seed efficiently?
        uint2 spatialSeed2 = fixSpatialSeed ? spatialSeed : (useTileSeed ? tileSeed : pixel);
        uint temporalSeed2 = fixTemporalSeed ? temporalSeed : (kCandidateSamples + 1 + gNumSpatialRounds) * params.seed + kCandidateSamples;
        var sg = TinyUniformSampleGenerator(spatialSeed2, temporalSeedOffset + temporalSeed2);

        // Compute offset into per-sample buffers. All samples are stored consecutively at this offset.
        const uint centralOffset = params.getReservoirOffset(pixel);
        PackedHitInfo centralPrimaryHitPacked;
        ShadingData centralPrimarySd = getPixelShadingData(pixel, centralPrimaryHitPacked);
        if (!isValidPackedHitInfo(centralPrimaryHitPacked)) return;

        // color averaging test

        // fetch temporal reservoir
        float2 motionVector = motionVectors[pixel];
        int2 prevPixel = pixel;

        bool foundTemporalSurface = true;

        if (gEnableTemporalReprojection)
        {
            prevPixel = pixel + motionVector * params.frameDim + (sampleNext2D(sg) * 1.f - 0.f);
        }

        if (!isValidScreenRegion(prevPixel) || !foundTemporalSurface) return;

        PackedHitInfo temporalPrimaryHitPacked;
        ShadingData temporalPrimarySd = getPixelTemporalShadingData(prevPixel, temporalPrimaryHitPacked);
        if (!isValidPackedHitInfo(temporalPrimaryHitPacked)) return;

        const uint temporalOffset = params.getReservoirOffset(prevPixel);

        // retrace path
        PathReservoir centralReservoir = outputReservoirs[centralOffset];
        PathReservoir temporalReservoir = temporalReservoirs[temporalOffset];
        retracePath(0, centralReservoir, temporalReservoir, centralOffset, centralPrimaryHitPacked, centralPrimarySd, temporalPrimaryHitPacked, temporalPrimarySd);
    }

    void retracePath(const uint id,
                     const in PathReservoir centralReservoir, const in PathReservoir temporalReservoir,
                     const uint centralOffset,
                     const PackedHitInfo centralPrimaryHitPacked, const ShadingData centralPrimarySd,
                     const PackedHitInfo temporalPrimaryHitPacked, const ShadingData temporalPrimarySd)
    {
        // talbot MIS
        // compute mis weight for current pixel

        HitInfo dstRcPrevVertexHit;
        HitInfo dstRcPrevVertexHit2;
        float3 dstRcPrevVertexWo;
        float3 dstRcPrevVertexWo2;
        float3 Tp;
        float3 Tp2;

        // write to memory
        if (centralReservoir.pathFlags.rcVertexLength() > 1)
        {
            Tp = traceHybridShiftRays(params, true, temporalPrimaryHitPacked, temporalPrimarySd, centralReservoir, dstRcPrevVertexHit, dstRcPrevVertexWo);
            setReconnectionData(id, centralOffset, 0, ReconnectionData(dstRcPrevVertexHit, dstRcPrevVertexWo, Tp));
        }
        if (temporalReservoir.pathFlags.rcVertexLength() > 1)
        {
            Tp2 = traceHybridShiftRays(params, false, centralPrimaryHitPacked, centralPrimarySd, temporalReservoir, dstRcPrevVertexHit2, dstRcPrevVertexWo2);
            setReconnectionData(id, centralOffset, 1, ReconnectionData(dstRcPrevVertexHit2, dstRcPrevVertexWo2, Tp2));
        }
    }

    void setReconnectionData(const uint id, const uint offset, const uint i, const in ReconnectionData data)
    {
        switch(id)
        {
            case 0:
                reconnectionDataBuffer[offset].data[i] = data;
                break;
        }
    }

    /** Entry point for merge pass.
        \param[in] pixel Pixel coordinates.
    */
    void execute(const uint2 _pixel)
    {
        const uint2 pixel = _pixel;

        if (any(pixel >= params.frameDim)) return;

        printSetPixel(pixel);
        logSetPixel(pixel);

        ReSTIR(pixel);
    }
};

cbuffer CB
{
    PathRetracePass gPathRetracePass;
}


[numthreads(16, 16, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    gPathRetracePass.execute(dispatchThreadId.xy);
}
