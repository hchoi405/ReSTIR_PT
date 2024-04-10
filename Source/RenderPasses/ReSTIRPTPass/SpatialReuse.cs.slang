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
import Utils.Math.MathHelpers;
import LoadShadingData;
import Rendering.Materials.MaterialShading;
import RenderPasses.Shared.Denoising.NRDData;
import RenderPasses.Shared.Denoising.NRDBuffers;
import RenderPasses.Shared.Denoising.NRDConstants;
import NRDHelpers;

struct PathReusePass
{
    static const uint kNeighborOffsetCount = NEIGHBOR_OFFSET_COUNT;
    static const uint kNeighborOffsetMask = kNeighborOffsetCount - 1;

    // Resources
    RestirPathTracerParams params;                        ///< Runtime parameters.

    Texture2D<PackedHitInfo> vbuffer;                     ///< Fullscreen V-buffer for the primary hits.
    Texture1D<float2> neighborOffsets;

    ByteAddressBuffer nRooksPattern;

    RWTexture2D<float4> outputColor;                      ///< Output resolved color.
    RWTexture2D<float4> outputColor2;                      ///< Output resolved color.
    RWTexture2D<float4> outputIndirect;                      ///< Output resolved color.
    StructuredBuffer<PathReservoir> outputReservoirs;     // reservoir from previous pass
    RWStructuredBuffer<PathReservoir> temporalReservoirs; // resulting reservoir for next frame
    StructuredBuffer<PixelReconnectionData> reconnectionDataBuffer;
    StructuredBuffer<PathReuseMISWeight> misWeightBuffer;

    StructuredBuffer<PathReservoir> outputReservoirs2;     // reservoir from previous pass
    RWStructuredBuffer<PathReservoir> temporalReservoirs2; // resulting reservoir for next frame
    StructuredBuffer<PixelReconnectionData> reconnectionDataBuffer2;

    RWTexture2D<float4> outputNRDDiffuseRadianceHitDist;    ///< Output resolved diffuse color in .rgb and hit distance in .a for NRD. Only valid if kOutputNRDData == true.
    RWTexture2D<float4> outputNRDSpecularRadianceHitDist;   ///< Output resolved specular color in .rgb and hit distance in .a for NRD. Only valid if kOutputNRDData == true.
    RWTexture2D<float4> outputNRDResidualRadianceHitDist;   ///< Output resolved residual color in .rgb and hit distance in .a for NRD. Only valid if kOutputNRDData == true.
    Texture2D<float4> primaryHitEmission;                     ///< Output per-pixel primary hit emission. Only valid if kOutputNRDData == true.

    int gSpatialRoundId;
    int  gNumSpatialRounds;
    uint gSpatialReusePattern;
    // for default pattern
    int gNeighborCount;
    float gGatherRadius;
    // for small window
    int gSmallWindowRadius;

    bool gIsLastRound;

    bool gFeatureBasedRejection;

    uint gSppId;

    bool fixSpatialSeed;
    uint spatialSeed;
    bool fixTemporalSeed;
    uint temporalSeed;
    uint temporalSeedOffset;

    uint gTileWidth;
    bool useTileSeed;

    Texture2D<float4> directLighting;
    bool useDirectLighting;

    bool isValidPackedHitInfo(PackedHitInfo packed)
    {
        return packed.x != 0;
    }

    bool isValidScreenRegion(int2 pixel) { return all(pixel >= 0 && pixel < params.frameDim); }

    bool isValidGeometry(ShadingData centralSd, ShadingData neighborSd)
    {
        if (!gFeatureBasedRejection) return true;
        float3 camPos = gScene.camera.data.posW;
        float centralDist = distance(camPos, centralSd.posW);
        float neighborDist = distance(camPos, neighborSd.posW);
        return dot(centralSd.N, neighborSd.N) >= 0.5f && abs(centralDist - neighborDist) < 0.1f * centralDist;
    }

    ShadingData getPixelShadingData(int2 pixel, out PackedHitInfo PrimaryHitPacked)
    {
        ShadingData sd = {};
        Ray ray = gScene.camera.computeRayPinhole(pixel, params.frameDim);
        PrimaryHitPacked = vbuffer[pixel];
        if (isValidPackedHitInfo(PrimaryHitPacked))
        {
            HitInfo PrimaryHit; PrimaryHit.unpack(PrimaryHitPacked);

            TriangleHit th = PrimaryHit.getTriangleHit();
            sd = loadShadingData(PrimaryHit, -ray.dir, true);
        }
        return sd;
    }

    int getNeighborCount()
    {
        if (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathReuse) return 16; //include self
        else
        {
            if (SpatialReusePattern(gSpatialReusePattern) == SpatialReusePattern::Default)
            {
                return gNeighborCount; // does not include self
            }
            else if (SpatialReusePattern(gSpatialReusePattern) == SpatialReusePattern::SmallWindow)
            {
                int smallWindowDiameter = 2 * gSmallWindowRadius + 1;
                return smallWindowDiameter * smallWindowDiameter; // count self, but not use self as neighbor
            }
            else if (SpatialReusePattern(gSpatialReusePattern) == SpatialReusePattern::Tile)
            {
                return gNeighborCount;
            }
        }
        return 0;
    }

    int2 getPathReuseNextNeighborPixel(int4 NRookQuery, int2 pixel, int i)
    {
        //
        if (PathReusePattern(gSpatialReusePattern) == PathReusePattern::Block)
        {
            int2 block = pixel / 4;
            return 4 * block + int2(i % 4, i / 4);
        }
        else
        {
            // fetch neighbors
            int groupId = NRookQuery.z;
            uint2 words = nRooksPattern.Load2(NRookQuery.w * 256 + groupId * 8);
            int rowId = (words[i / 8] >> (4 * (i % 8))) & 0xF;

            return int2(i, rowId) - NRookQuery.xy + pixel;
        }
    }

    int2 getNextNeighborPixel(const uint startIndex, int2 pixel, int i)
    {
        int2 neighborPixel = int2(0,0);

        if (SpatialReusePattern(gSpatialReusePattern) == SpatialReusePattern::Default)
        {
            uint neighborIndex = (startIndex + i) & kNeighborOffsetMask;
            neighborPixel = pixel + int2(neighborOffsets[neighborIndex] * gGatherRadius);
        }
        else if (SpatialReusePattern(gSpatialReusePattern) == SpatialReusePattern::SmallWindow)
        {
            int smallWindowDiameter = 2 * gSmallWindowRadius + 1;
            neighborPixel = pixel + int2(-gSmallWindowRadius + (i % smallWindowDiameter),
                -gSmallWindowRadius + (i / smallWindowDiameter));
            if (all(neighborPixel == pixel)) neighborPixel = int2(-1);
        }
        else if (SpatialReusePattern(gSpatialReusePattern) == SpatialReusePattern::Tile)
        {
            uint2 tileId = pixel / gTileWidth;
            uint2 tileOffset = tileId * gTileWidth;
            uint2 tileDim = min(params.frameDim - tileOffset, gTileWidth);
            uint neighborIndex = (startIndex + i) & kNeighborOffsetMask;
            neighborPixel = tileOffset + uint2(abs(neighborOffsets[neighborIndex]) * tileDim);
            if (all(neighborPixel == pixel)) neighborPixel = int2(-1);
        }

        return neighborPixel;
    }

    void ReSTIR(const uint2 pixel)
    {
        uint2 tileSeed = pixel % gTileWidth;

        uint2 spatialSeed2 = fixSpatialSeed ? spatialSeed : (useTileSeed ? tileSeed : pixel);
        uint temporalSeed2 = fixTemporalSeed ? temporalSeed : (kCandidateSamples + 1 + gNumSpatialRounds) * params.seed + kCandidateSamples + 1 + gSpatialRoundId;

        // Compute offset into per-sample buffers. All samples are stored consecutively at this offset.
        const uint centralOffset = params.getReservoirOffset(pixel);
        PackedHitInfo centralPrimaryHitPacked;
        ShadingData centralPrimarySd = getPixelShadingData(pixel, centralPrimaryHitPacked);

        if (!isValidPackedHitInfo(centralPrimaryHitPacked)) return;

        //
        // Reuse the path
        var sg = TinyUniformSampleGenerator(spatialSeed2, temporalSeedOffset + temporalSeed2);
        PathReservoir centerReservoir = outputReservoirs[centralOffset];
        var dstReservoir = reusePath(0, centerReservoir, pixel, centralOffset, sg, centralPrimaryHitPacked, centralPrimarySd);

        // Store the resulting reservoir for the next frame
        if (PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathReuse)
            temporalReservoirs[centralOffset] = dstReservoir;

        // Calculate color
        float3 color = dstReservoir.F * dstReservoir.weight;
        if (any(isnan(color) || isinf(color) || color < 0.f)) color = 0.f;
        if (gIsLastRound)
        {
            outputIndirect[pixel] += float4(color / kSamplesPerPixel, 1.f);

            if (useDirectLighting)
            {
                color += directLighting[pixel].rgb;
                if (any(isnan(color) || isinf(color))) color = 0.f;
            }

            outputColor[pixel] += float4(color / kSamplesPerPixel, 1.f);

            // Output Denoiser Data (developed for NRD v2.12, doesn't guarantee to work with the latest version)
            if (kOutputNRDData && PathSamplingMode(kPathSamplingMode) == PathSamplingMode::ReSTIR)
            {
                float3 diffuseRadiance = 0.f;
                float3 specularRadiance = 0.f;
                float3 residualRadiance = 0.f;
                float hitDist = 0.f;
                float3 reflectance = 0.f;
                float3 radiance = 0.f;
                NRDPathType pathType = NRDPathType::Residual;

                //
                if (ShiftMapping(kShiftStrategy) == ShiftMapping::Reconnection ||
                    ShiftMapping(kShiftStrategy) == ShiftMapping::Hybrid && dstReservoir.pathFlags.rcVertexLength() == 1) // rcVertexHit must exists
                {
                    if (dstReservoir.rcVertexHit.instanceID == 0xffffffff)
                    {
                        hitDist = kNRDInvalidPathLength;
                    }
                    else
                    {
                        bool isDiffusePrimaryHit = !dstReservoir.pathFlags.decodeIsSpecularBounce(true);
                        bool isSpecularPrimaryHit = dstReservoir.pathFlags.decodeIsSpecularBounce(true) && !dstReservoir.pathFlags.decodeIsDeltaEvent(true);

                        reflectance = computeSampleReflectance(kUseNRDDemodulation, isDiffusePrimaryHit, isSpecularPrimaryHit, centralPrimarySd);

                        ShadingData RcVertexSd = loadShadingDataWithPrevVertexPosition(dstReservoir.rcVertexHit.getHitInfo(), centralPrimarySd.posW, false);
                        hitDist = length(RcVertexSd.posW - centralPrimarySd.posW);

                        pathType = NRDPathType::Residual;
                        if (isDiffusePrimaryHit) pathType = NRDPathType::Diffuse;
                        else if (isSpecularPrimaryHit) pathType = NRDPathType::Specular;

                        radiance = dstReservoir.F * dstReservoir.weight;
                    }
                }
                else
                {
                    HitInfo centralPrimaryHit; centralPrimaryHit.unpack(centralPrimaryHitPacked);
                    Ray ray = Ray(gScene.camera.getPosition(), -centralPrimarySd.V, 0, kRayTMax);

                    traceDenoiserData(params, centralPrimaryHitPacked, centralPrimarySd,
                                      dstReservoir.pathFlags, dstReservoir.initRandomSeed, hitDist, pathType, reflectance);

                    radiance = dstReservoir.F * dstReservoir.weight;
                }

                if (useDirectLighting)
                    radiance += directLighting[pixel].rgb;

                reflectance = max(0.04f, reflectance);
                float3 emission = primaryHitEmission[pixel].rgb;
                float3 demodulatedRadiance = max(0.f, (radiance - emission)) / reflectance;

                switch (pathType)
                {
                case NRDPathType::Diffuse:
                    diffuseRadiance += demodulatedRadiance;
                    break;
                case NRDPathType::Specular:
                    specularRadiance += demodulatedRadiance;
                    break;
                default:
                    // Do not demodulate residual.
                    residualRadiance += radiance;
                    break;
                }

                float invSpp = 1.f / kSamplesPerPixel;

                if (gSppId == 0)
                {
                    outputNRDDiffuseRadianceHitDist[pixel] = float4(invSpp * diffuseRadiance, invSpp * hitDist);
                    outputNRDSpecularRadianceHitDist[pixel] = float4(invSpp * specularRadiance, invSpp * hitDist);
                    outputNRDResidualRadianceHitDist[pixel] = float4(invSpp * residualRadiance, invSpp * hitDist);
                }
                else
                {
                    outputNRDDiffuseRadianceHitDist[pixel] += float4(invSpp * diffuseRadiance, invSpp * hitDist);
                    outputNRDSpecularRadianceHitDist[pixel] += float4(invSpp * specularRadiance, invSpp * hitDist);
                    outputNRDResidualRadianceHitDist[pixel] += float4(invSpp * residualRadiance, invSpp * hitDist);
                }
            }
        }

        ////
        // Reuse the path
        var sg2 = TinyUniformSampleGenerator(spatialSeed2, temporalSeedOffset + temporalSeed2 + 1000000);
        PathReservoir centerReservoir2 = outputReservoirs2[centralOffset];
        var dstReservoir2 = reusePath(1, centerReservoir2, pixel, centralOffset, sg2, centralPrimaryHitPacked, centralPrimarySd);

        // Store the resulting reservoir for the next frame
        if (PathSamplingMode(kPathSamplingMode) != PathSamplingMode::PathReuse)
            temporalReservoirs2[centralOffset] = dstReservoir2;

        if (gIsLastRound)
        {
            float3 color2 = dstReservoir2.F * dstReservoir2.weight;
            if (any(isnan(color2) || isinf(color2) || color2 < 0.f)) color2 = 0.f;

            if (useDirectLighting)
            {
                color2 += directLighting[pixel].rgb;
                if (any(isnan(color2) || isinf(color2))) color2 = 0.f;
            }

            outputColor2[pixel] += float4(color2 / kSamplesPerPixel, 1.f);
        }
    }

    PathReservoir reusePath(
        //
        const uint id,
        const in PathReservoir centralReservoir,
        //
        const uint2 pixel, const uint centralOffset,
        inout TinyUniformSampleGenerator sg,
        PackedHitInfo centralPrimaryHitPacked, ShadingData centralPrimarySd)
    {
        PathReservoir dstReservoir = centralReservoir;

        float3 initialColor = dstReservoir.F * dstReservoir.weight;

        float centralM = dstReservoir.M;

        if (PathSamplingMode(kPathSamplingMode) == PathSamplingMode::PathReuse ||
            (ReSTIRMISKind(kSpatialReSTIRMISKind) == ReSTIRMISKind::Talbot || ReSTIRMISKind(kSpatialReSTIRMISKind) == ReSTIRMISKind::Pairwise))
        {
            dstReservoir.init();
        }
        else
        {
            dstReservoir.prepareMerging();
        }

        ReconnectionData dummyRcData;
        dummyRcData.Init();

        int neighborCount = getNeighborCount();
        const uint startIndex = sampleNext1D(sg) * kNeighborOffsetCount;

        /////////////////////
        /// PAIRWISE RMIS ///
        /////////////////////
        if (ReSTIRMISKind(kSpatialReSTIRMISKind) == ReSTIRMISKind::Pairwise)
        {
            int validNeighborCount = 0;
            float canonicalWeight = 1;

            for (int i = 0; i < neighborCount; ++i)
            {
                int2 neighborPixel = getNextNeighborPixel(startIndex, pixel, i);

                if (!isValidScreenRegion(neighborPixel)) continue;

                PackedHitInfo neighborPrimaryHitPacked;
                ShadingData neighborPrimarySd = getPixelShadingData(neighborPixel, neighborPrimaryHitPacked);
                if (!isValidPackedHitInfo(neighborPrimaryHitPacked)) continue;
                if (!isValidGeometry(centralPrimarySd, neighborPrimarySd)) continue;

                PathReservoir neighborReservoir = getOutputReservoir(id, params.getReservoirOffset(neighborPixel));

                float dstJacobian;

                validNeighborCount++;

                float prefix_approxPdf = 0.f;

                float prefixJacobian;

                ReconnectionData rcData;
                if (ShiftMapping(kShiftStrategy) == ShiftMapping::Hybrid && centralReservoir.pathFlags.rcVertexLength() > 1)
                {
                    rcData = getReconnectionData(id, centralOffset, 2 * i);
                }
                else
                    rcData = dummyRcData;

                float3 prefixIntegrand = computeShiftedIntegrand(params, prefixJacobian, neighborPrimaryHitPacked, neighborPrimarySd,
                    centralPrimarySd, centralReservoir, rcData, true);

                prefix_approxPdf = PathReservoir::computeWeight(prefixIntegrand) * prefixJacobian;

                canonicalWeight += 1;
                if (prefix_approxPdf > 0.f)
                    canonicalWeight -= prefix_approxPdf * neighborReservoir.M / (prefix_approxPdf * neighborReservoir.M + centralReservoir.M * PathReservoir::computeWeight(centralReservoir.F) / (neighborCount));

                PathReservoir tempDstReservoir = dstReservoir;

                if (ShiftMapping(kShiftStrategy) == ShiftMapping::Hybrid && neighborReservoir.pathFlags.rcVertexLength() > 1)
                {
                    rcData = getReconnectionData(id, centralOffset, 2 * i + 1);
                }
                else
                    rcData = dummyRcData;

                bool possibleToBeSelected = shiftAndMergeReservoir(params, false, dstJacobian, centralPrimaryHitPacked, centralPrimarySd, tempDstReservoir,
                    neighborPrimarySd, neighborReservoir, rcData, true, sg, true, 1.f, true); // "true" means hypothetically selected as the sample

                float neighborWeight = 0.f;

                if (possibleToBeSelected)
                {
                    neighborWeight = PathReservoir::computeWeight(neighborReservoir.F) / dstJacobian * neighborReservoir.M
                        / ((PathReservoir::computeWeight(neighborReservoir.F) / dstJacobian) * neighborReservoir.M + PathReservoir::computeWeight(tempDstReservoir.F) * centralReservoir.M / (neighborCount));
                    if (isnan(neighborWeight) || isinf(neighborWeight)) neighborWeight = 0.f;
                }

                mergeReservoirWithResamplingMIS(params, tempDstReservoir.F, dstJacobian, dstReservoir, tempDstReservoir, neighborReservoir, sg, true, neighborWeight);
            }

            mergeReservoirWithResamplingMIS(params, centralReservoir.F, 1.f, dstReservoir, centralReservoir, centralReservoir, sg, true, canonicalWeight);

            if (dstReservoir.weight > 0)
            {
                dstReservoir.finalizeGRIS();
                dstReservoir.weight /= (validNeighborCount + 1); // compensate for the fact that pairwise resampling MIS was not divided by (k+1)
            }
        }

        if (dstReservoir.weight < 0.f) dstReservoir.weight = 0.f;
        if (isnan(dstReservoir.weight) || isinf(dstReservoir.weight)) dstReservoir.weight = 0.f;

        return dstReservoir;
    }

    PathReservoir getOutputReservoir(const uint id, const uint offset)
    {
        switch (id)
        {
        case 0:
            return outputReservoirs[offset];
        case 1:
            return outputReservoirs2[offset];
        }
        PathReservoir emptyReservoir;
        return emptyReservoir;
    }

    ReconnectionData getReconnectionData(const uint id, const uint offset, const uint i)
    {
        switch (id)
        {
        case 0:
            return reconnectionDataBuffer[offset].data[i];
        case 1:
            return reconnectionDataBuffer2[offset].data[i];
        }
        ReconnectionData emptyRcData;
        return emptyRcData;
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
    PathReusePass gPathReusePass;
}


[numthreads(16, 16, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    gPathReusePass.execute(dispatchThreadId.xy);
}
