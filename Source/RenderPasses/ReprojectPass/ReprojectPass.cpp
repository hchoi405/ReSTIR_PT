/***************************************************************************
 # Copyright (c) 2015-22, NVIDIA CORPORATION. All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without
 # modification, are permitted provided that the following conditions
 # are met:
 #  * Redistributions of source code must retain the above copyright
 #    notice, this list of conditions and the following disclaimer.
 #  * Redistributions in binary form must reproduce the above copyright
 #    notice, this list of conditions and the following disclaimer in the
 #    documentation and/or other materials provided with the distribution.
 #  * Neither the name of NVIDIA CORPORATION nor the names of its
 #    contributors may be used to endorse or promote products derived
 #    from this software without specific prior written permission.
 #
 # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
 # EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 # PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 # PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 # OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 # (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 # OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 **************************************************************************/
#include "ReprojectPass.h"
#include "RenderGraph/RenderPassLibrary.h"

// const RenderPass::Info ReprojectPass::kInfo{"ReprojectPass", "Reprojection of illumination and corresponding stats."};

namespace
{
    const char kDesc[] = "Reprojection Pass";

    const char kPackLinearZAndNormalShader[] = "RenderPasses/ReprojectPass/PackLinearZAndNormal.ps.slang";
    const char kReprojectShader[] = "RenderPasses/ReprojectPass/Reproject.ps.slang";

    const char kSeparateBuffer[] = "separateBuffer";
    const char kSingleReprojFrame[] = "singleReprojFrame";

    // Input buffer names (required inputs for SVGF)
    const char kInputBufferDiffuseOpacity[] = "DiffuseOpacity";
    const char kInputBufferSpecRough[] = "SpecRough";
    const char kInputBufferColor[] = "Color";
    const char kInputBufferEmission[] = "Emission";
    const char kInputBufferWorldPosition[] = "WorldPosition";
    const char kInputBufferWorldNormal[] = "WorldNormal";
    const char kInputBufferPosNormalFwidth[] = "PositionNormalFwidth";
    const char kInputBufferLinearZ[] = "LinearZ";
    const char kInputBufferMotionVector[] = "MotionVec";

    const char kOutputCurrent[] = "Current";
    const char kOutputAlbedo[] = "Albedo";
    // const char kOutputAlpha[] = "Alpha";
    // const char kOutputSuccess[] = "Success";

    const char kOutputAccumulated[] = "Accumulated";
    const char kOutputHistory[] = "History";
    const char kOutputLength[] = "Length";

    // Separate buffers
    const char kOutputAccumulate2[] = "Accumulated2";
    const char kOutputHistory2[] = "History2";
    const char kOutputLength2[] = "Length2";

    // Internal buffer names
    const char kInternalBufferPreviousLinearZAndNormal[] = "Previous Linear Z and Packed Normal";
}

// Don't remove this. it's required for hot-reload to function properly
extern "C" __declspec(dllexport) const char *getProjDir()
{
    return PROJECT_DIR;
}

extern "C" __declspec(dllexport) void getPasses(Falcor::RenderPassLibrary &lib)
{
    lib.registerClass("ReprojectPass", kDesc, ReprojectPass::create);
}

ReprojectPass::SharedPtr ReprojectPass::create(RenderContext *pRenderContext, const Dictionary &dict)
{
    SharedPtr pPass = SharedPtr(new ReprojectPass(dict));
    return pPass;
}

ReprojectPass::ReprojectPass(const Dictionary &dict)
{
    mpPackLinearZAndNormal = FullScreenPass::create(kPackLinearZAndNormalShader);
    mpReprojection = FullScreenPass::create(kReprojectShader);

    assert(mpPackLinearZAndNormal && mpReprojection);

    // Parse dictionary
    for (const auto &[key, value] : dict)
    {
        if (key == kSeparateBuffer)
        {
            bool tmp = value;
            mSeparateBuffer = tmp;
        }
        else if (key == kSingleReprojFrame)
        {
            uint64_t tmp = value;
            mSingleReprojFrame = tmp;
        }
        else
        {
            logWarning("Unknown field '" + key + "' in a ReprojectPass dictionary");
        }
    }
    mFrameCount = 0;
}

std::string ReprojectPass::getDesc() { return kDesc; }

Dictionary ReprojectPass::getScriptingDictionary()
{
    Dictionary dict;
    dict[kSeparateBuffer] = mSeparateBuffer;
    dict[kSingleReprojFrame] = mSingleReprojFrame;
    return dict;
}

/*
Reproject:
  - takes: motion, color, prevLighting, linearZ, prevLinearZ, accumlen
    returns: illumination, accumlength
*/
RenderPassReflection ReprojectPass::reflect(const CompileData &compileData)
{
    // Define the required resources here
    RenderPassReflection reflector;

    reflector.addInput(kInputBufferDiffuseOpacity, "DiffuseOpacity");
    reflector.addInput(kInputBufferSpecRough, "SpecRough");
    reflector.addInput(kInputBufferColor, "Color");
    reflector.addInput(kInputBufferEmission, "Emission");
    reflector.addInput(kInputBufferWorldPosition, "World Position");
    reflector.addInput(kInputBufferWorldNormal, "World Normal");
    reflector.addInput(kInputBufferPosNormalFwidth, "PositionNormalFwidth");
    reflector.addInput(kInputBufferLinearZ, "LinearZ");
    reflector.addInput(kInputBufferMotionVector, "Motion vectors");

    reflector.addOutput(kOutputCurrent, "Current").format(ResourceFormat::RGBA32Float);
    reflector.addOutput(kOutputAlbedo, "Albedo").format(ResourceFormat::RGBA32Float);
    // reflector.addOutput(kOutputSuccess, "Success").format(ResourceFormat::R16Float);

    // Buffer 1
    reflector.addOutput(kOutputAccumulated, "Accumulated").format(ResourceFormat::RGBA32Float);
    reflector.addOutput(kOutputHistory, "History").format(ResourceFormat::RGBA32Float);
    reflector.addOutput(kOutputLength, "Length").format(ResourceFormat::RG16Float);

    // Buffer 2
    reflector.addOutput(kOutputAccumulate2, "Accumulated2").format(ResourceFormat::RGBA32Float);
    reflector.addOutput(kOutputHistory2, "History2").format(ResourceFormat::RGBA32Float);
    reflector.addOutput(kOutputLength2, "Length2").format(ResourceFormat::RG16Float);

    reflector.addInternal(kInternalBufferPreviousLinearZAndNormal, "Previous Linear Z and Packed Normal")
        .format(ResourceFormat::RGBA32Float)
        .bindFlags(Resource::BindFlags::RenderTarget | Resource::BindFlags::ShaderResource);

    return reflector;
}

void ReprojectPass::compile(RenderContext *pRenderContext, const CompileData &compileData)
{
    printf("[ReprojectPass] compile\n");
    allocateFbos(compileData.defaultTexDims, pRenderContext);
    mBuffersNeedClear = true;
    mFrameCount = 0;
}

void ReprojectPass::execute(RenderContext *pRenderContext, const RenderData &renderData)
{
    const auto frameCount = gpFramework->getGlobalClock().getFrame();

    if (mBuffersNeedClear)
    {
        clearBuffers(pRenderContext, renderData);
        mBuffersNeedClear = false;
        // gpFramework->getGlobalClock().setTime(0);
        printf("[ReprojectPass] Cleared (mFrameCount:%llu, global frameCount:%llu)\n", mFrameCount, frameCount);
    }

    if (mFrameCount == mSingleReprojFrame)
    {
        mSeparateBuffer = false;
        printf("[ReprojectPass] Disabled (mFrameCount:%llu, global frameCount:%llu)\n", mFrameCount, frameCount);
    }

    Texture::SharedPtr pDiffuseOpacityTexture = renderData[kInputBufferDiffuseOpacity]->asTexture();
    Texture::SharedPtr pSpecRoughTexture = renderData[kInputBufferSpecRough]->asTexture();
    Texture::SharedPtr pColorTexture = renderData[kInputBufferColor]->asTexture();
    Texture::SharedPtr pEmissionTexture = renderData[kInputBufferEmission]->asTexture();
    Texture::SharedPtr pWorldPositionTexture = renderData[kInputBufferWorldPosition]->asTexture();
    Texture::SharedPtr pWorldNormalTexture = renderData[kInputBufferWorldNormal]->asTexture();
    Texture::SharedPtr pPosNormalFwidthTexture = renderData[kInputBufferPosNormalFwidth]->asTexture();
    Texture::SharedPtr pLinearZTexture = renderData[kInputBufferLinearZ]->asTexture();
    Texture::SharedPtr pMotionVectorTexture = renderData[kInputBufferMotionVector]->asTexture();

    Texture::SharedPtr pCurrentTexture = renderData[kOutputCurrent]->asTexture();
    Texture::SharedPtr pOutputAlbedo = renderData[kOutputAlbedo]->asTexture();
    // Texture::SharedPtr pOutputSuccess = renderData[kOutputSuccess]->asTexture();

    Texture::SharedPtr pAccumTexture = renderData[kOutputAccumulated]->asTexture();
    Texture::SharedPtr pHistoryTexture = renderData[kOutputHistory]->asTexture();
    Texture::SharedPtr pOutputLength = renderData[kOutputLength]->asTexture();

    Texture::SharedPtr pAccumTexture2 = renderData[kOutputAccumulate2]->asTexture();
    Texture::SharedPtr pHistoryTexture2 = renderData[kOutputHistory2]->asTexture();
    Texture::SharedPtr pOutputLength2 = renderData[kOutputLength2]->asTexture();

    if (mEnabled)
    {
        // Grab linear z and its derivative and also pack the normal into
        // the last two channels of the mpLinearZAndNormalFbo.
        computeLinearZAndNormal(pRenderContext, pLinearZTexture, pWorldNormalTexture);

        // Demodulate input color & albedo to get illumination and lerp in
        // reprojected filtered illumination from the previous frame.
        // Stores the result and an updated per-pixel accumulated length in mpCurReprojFbo.
        Texture::SharedPtr pPrevLinearZAndNormalTexture =
            renderData[kInternalBufferPreviousLinearZAndNormal]->asTexture();
        computeReprojection(frameCount, pRenderContext, mpCurReprojFbo, mpPrevReprojFbo,
                            pDiffuseOpacityTexture, pSpecRoughTexture, pColorTexture,
                            pEmissionTexture, pMotionVectorTexture, pPosNormalFwidthTexture,
                            pPrevLinearZAndNormalTexture);

        pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(0)->getSRV(), pCurrentTexture->getRTV());
        pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(7)->getSRV(), pOutputAlbedo->getRTV());

        pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(1)->getSRV(), pAccumTexture->getRTV());
        pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(2)->getSRV(), pHistoryTexture->getRTV());
        pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(3)->getSRV(), pOutputLength->getRTV());

        if (mSeparateBuffer)
        {
            pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(4)->getSRV(), pAccumTexture2->getRTV());
            pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(5)->getSRV(), pHistoryTexture2->getRTV());
            pRenderContext->blit(mpCurReprojFbo[0]->getColorTexture(6)->getSRV(), pOutputLength2->getRTV());
        }

        // Swap resources so we're ready for next frame.
        std::swap(mpCurReprojFbo[0], mpPrevReprojFbo[0]);

        pRenderContext->blit(mpLinearZAndNormalFbo->getColorTexture(0)->getSRV(),
                             pPrevLinearZAndNormalTexture->getRTV());
    }
    else
    {
        pRenderContext->blit(pColorTexture->getSRV(), pAccumTexture->getRTV());
    }

    mFrameCount++;
}

void ReprojectPass::allocateFbos(uint2 dim, RenderContext *pRenderContext)
{
    {
        Fbo::Desc desc;
        desc.setSampleCount(0);
        desc.setColorTarget(0, Falcor::ResourceFormat::RGBA32Float); // (0) current

        desc.setColorTarget(1, Falcor::ResourceFormat::RGBA32Float); // (1) accumulated
        desc.setColorTarget(2, Falcor::ResourceFormat::RGBA32Float); // (2) history
        desc.setColorTarget(3, Falcor::ResourceFormat::RG16Float);   // (3) accum/history length

        desc.setColorTarget(4, Falcor::ResourceFormat::RGBA32Float); // (4) accumulated2
        desc.setColorTarget(5, Falcor::ResourceFormat::RGBA32Float); // (5) history2
        desc.setColorTarget(6, Falcor::ResourceFormat::RG16Float);   // (6) accum/history length2

        desc.setColorTarget(7, Falcor::ResourceFormat::RGBA32Float); // (7) Albedo
        // desc.setColorTarget(7, Falcor::ResourceFormat::R16Float); // (7) Success
        mpCurReprojFbo[0] = Fbo::create2D(dim.x, dim.y, desc);
        mpCurReprojFbo[1] = Fbo::create2D(dim.x, dim.y, desc);
        mpPrevReprojFbo[0] = Fbo::create2D(dim.x, dim.y, desc);
        mpPrevReprojFbo[1] = Fbo::create2D(dim.x, dim.y, desc);
    }

    {
        // Screen-size RGBA32F buffer for linear Z, derivative, and packed normal
        Fbo::Desc desc;
        desc.setColorTarget(0, Falcor::ResourceFormat::RGBA32Float);
        mpLinearZAndNormalFbo = Fbo::create2D(dim.x, dim.y, desc);
    }

    mBuffersNeedClear = true;
}

void ReprojectPass::clearBuffers(RenderContext *pRenderContext, const RenderData &renderData)
{
    pRenderContext->clearFbo(mpLinearZAndNormalFbo.get(), float4(0), 1.0f, 0, FboAttachmentType::All);

    pRenderContext->clearFbo(mpCurReprojFbo[0].get(), float4(0), 1.0f, 0, FboAttachmentType::All);
    pRenderContext->clearFbo(mpPrevReprojFbo[0].get(), float4(0), 1.0f, 0, FboAttachmentType::All);

    if (mSeparateBuffer)
    {
        pRenderContext->clearFbo(mpCurReprojFbo[1].get(), float4(0), 1.0f, 0, FboAttachmentType::All);
        pRenderContext->clearFbo(mpPrevReprojFbo[1].get(), float4(0), 1.0f, 0, FboAttachmentType::All);
    }

    pRenderContext->clearTexture(renderData[kInternalBufferPreviousLinearZAndNormal]->asTexture().get());
}

void ReprojectPass::computeLinearZAndNormal(RenderContext *pRenderContext,
                                            Texture::SharedPtr pLinearZTexture,
                                            Texture::SharedPtr pWorldNormalTexture)
{
    auto perImageCB = mpPackLinearZAndNormal["PerImageCB"];
    perImageCB["gLinearZ"] = pLinearZTexture;
    perImageCB["gNormal"] = pWorldNormalTexture;

    mpPackLinearZAndNormal->execute(pRenderContext, mpLinearZAndNormalFbo);
}

void ReprojectPass::computeReprojection(uint64_t frameCount, RenderContext *pRenderContext,
                                        Fbo::SharedPtr curReprojFbo[2],
                                        Fbo::SharedPtr prevReprojFbo[2],
                                        Texture::SharedPtr pDiffuseOpacityTexture,
                                        Texture::SharedPtr pSpecRoughTexture,
                                        Texture::SharedPtr pColorTexture,
                                        Texture::SharedPtr pEmissionTexture,
                                        Texture::SharedPtr pMotionVectorTexture,
                                        Texture::SharedPtr pPositionNormalFwidthTexture,
                                        Texture::SharedPtr pPrevLinearZTexture)
{
    auto perImageCB = mpReprojection["PerImageCB"];

    // Setup textures for our reprojection shader pass
    perImageCB["gMotion"] = pMotionVectorTexture;
    perImageCB["gColor"] = pColorTexture;
    // perImageCB["gEmission"] = pEmissionTexture;
    perImageCB["gDiffuseOpacity"] = pDiffuseOpacityTexture;
    perImageCB["gSpecRough"] = pSpecRoughTexture;
    perImageCB["gPositionNormalFwidth"] = pPositionNormalFwidthTexture;
    perImageCB["gPrevLinearZAndNormal"] = pPrevLinearZTexture;
    perImageCB["gLinearZAndNormal"] = mpLinearZAndNormalFbo->getColorTexture(0);

    // Setup variables for our reprojection pass
    perImageCB["gAlpha"] = mAlpha;

    if (!mSeparateBuffer)
    {
        perImageCB["gPrevIllum"] = prevReprojFbo[0]->getColorTexture(1);
        perImageCB["gPrevLength"] = prevReprojFbo[0]->getColorTexture(3);
        perImageCB["gUsePrevAccum"] = true;
        mpReprojection->execute(pRenderContext, curReprojFbo[0]);
    }
    else
    {
        // Reproject buffers
        if (frameCount % 2 == 0)
        {
            // Previous frame (odd number) should not be accumulated, so use history here
            perImageCB["gPrevIllum"] = prevReprojFbo[0]->getColorTexture(2);  // use history
            perImageCB["gPrevIllum2"] = prevReprojFbo[0]->getColorTexture(4); // use accum
            // Update statistics for the current frame (even number)
            perImageCB["gUsePrevAccum"] = false;
        }
        else
        {
            // Previous frame (even number) should be accumulated, so use accum here
            perImageCB["gPrevIllum"] = prevReprojFbo[0]->getColorTexture(1);  // use accum
            perImageCB["gPrevIllum2"] = prevReprojFbo[0]->getColorTexture(5); // use history
            // Do not update statistics for the current frame (odd number)
            perImageCB["gUsePrevAccum"] = true;
        }
        perImageCB["gPrevLength"] = prevReprojFbo[0]->getColorTexture(3);
        perImageCB["gPrevLength2"] = prevReprojFbo[0]->getColorTexture(6);
        mpReprojection->execute(pRenderContext, curReprojFbo[0]);
    }
}

void ReprojectPass::renderUI(Gui::Widgets &widget)
{
    int dirty = 0;

    dirty |= (int)widget.checkbox("Enable?", mEnabled);
    dirty |= (int)widget.checkbox("Separate buffer?", mSeparateBuffer);

    // Reprojection
    widget.text("How much history should be used?");
    widget.text("    (alpha; 0 = full reuse; 1 = no reuse)");
    dirty |= (int)widget.var("Alpha", mAlpha, 0.0f, 1.0f, 0.001f);

    if (dirty)
        mBuffersNeedClear = true;
}
