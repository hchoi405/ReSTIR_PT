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
#include "CapturePass.h"
#include "RenderGraph/RenderPassLibrary.h"
#include <fmt/format.h>

#include <fstream>
#include <sstream>

namespace
{
    const char kDesc[] = "Capture pass";
    const char kDirectory[] = "directory";
    const char kChannels[] = "channels";
    const char kExitAtEnd[] = "exitAtEnd";
    const char kAccumulate[] = "accumulate";
    const char kAccumulateCount[] = "accumulateCount";
    const char kWriteStart[] = "writeStart";
    const char kWriteEnd[] = "writeEnd";
    const char kCaptureCameraMat[] = "captureCameraMat";
    const char kCaptureCameraMatOnly[] = "captureCameraMatOnly";
    const char kIncludeAlpha[] = "includeAlpha";
}

// Don't remove this. it's required for hot-reload to function properly
extern "C" __declspec(dllexport) const char *getProjDir()
{
    return PROJECT_DIR;
}

extern "C" __declspec(dllexport) void getPasses(Falcor::RenderPassLibrary &lib)
{
    lib.registerClass("CapturePass", kDesc, CapturePass::create);
}

CapturePass::SharedPtr CapturePass::create(RenderContext *pRenderContext, const Dictionary &dict)
{
    SharedPtr pPass = SharedPtr(new CapturePass(dict));
    return pPass;
}

CapturePass::CapturePass(const Dictionary &dict)
{
    parseDictionary(dict);

    if (mCaptureCameraMat)
    {
        char filename[100] = "";
        // Load sample file and find insert location
        sprintf(filename, "%s/../camera_matrices_template.h", mDirectory.c_str());
        std::ifstream inText(filename, std::ios_base::in);
        std::stringstream buffer;
        buffer << inText.rdbuf();
        mCameraMatTemplate = buffer.str();
    }

    CreateDirectoryA(mDirectory.c_str(), NULL);
}

std::string CapturePass::getDesc() { return kDesc; }

void CapturePass::parseDictionary(const Dictionary &dict)
{
    for (const auto &[key, value] : dict)
    {
        if (key == kDirectory)
        {
            std::string tmp = value;
            mDirectory = tmp;
        }
        else if (key == kChannels)
        {
            std::vector<std::string> channels = value;
            mChannels = channels;
        }
        else if (key == kExitAtEnd)
        {
            bool tmp = value;
            mExitAtEnd = tmp;
        }
        else if (key == kAccumulate)
        {
            bool tmp = value;
            mAccumulateSubFrames = tmp;
        }
        else if (key == kAccumulateCount)
        {
            int tmp = value;
            mAccumulateCount = value;
        }
        else if (key == kWriteStart)
        {
            int tmp = value;
            mWriteStart = value;
        }
        else if (key == kWriteEnd)
        {
            int tmp = value;
            mWriteEnd = value;
        }
        else if (key == kCaptureCameraMat)
        {
            bool tmp = value;
            mCaptureCameraMat = tmp;
        }
        else if (key == kCaptureCameraMatOnly)
        {
            bool tmp = value;
            mCaptureCameraMatOnly = tmp;
        }
        else if (key == kIncludeAlpha)
        {
            std::vector<std::string> includeAlpha = value;
            mIncludeAlpha = includeAlpha;
        }
    }
}

Dictionary CapturePass::getScriptingDictionary()
{
    Dictionary dict;
    dict[kDirectory] = mDirectory;
    dict[kChannels] = mChannels;
    dict[kExitAtEnd] = mExitAtEnd;
    dict[kAccumulate] = mAccumulateSubFrames;
    dict[kAccumulateCount] = mAccumulateCount;
    dict[kWriteStart] = mWriteStart;
    dict[kWriteEnd] = mWriteEnd;
    dict[kCaptureCameraMat] = mCaptureCameraMat;
    dict[kCaptureCameraMatOnly] = mCaptureCameraMatOnly;
    dict[kIncludeAlpha] = mIncludeAlpha;
    return dict;
}

RenderPassReflection CapturePass::reflect(const CompileData &compileData)
{
    // Define the required resources here
    RenderPassReflection reflector;
    for (size_t i = 0; i < mChannels.size(); ++i)
    {
        reflector.addInputOutput(mChannels[i], mChannels[i]);
    }
    return reflector;
}

void CapturePass::storeTexture(RenderContext *pRenderContext, const uint64_t frameID, const std::string &channelName, Texture::SharedPtr texture)
{
    char filename[100] = "";
    sprintf(filename, "%s/%s_%04llu.exr", mDirectory.c_str(), channelName.c_str(), frameID);

    // Include alpha channel for specific channel only
    bool includeAlpha = false;
    if (std::find(mIncludeAlpha.begin(), mIncludeAlpha.end(), channelName) != mIncludeAlpha.end())
        includeAlpha = true;

    // Create new texture for the format not supported to be saved as exr
    switch (texture->getFormat())
    {
    case ResourceFormat::RGBA8Unorm:
    {
        auto tex = Texture::create2D(texture->getWidth(), texture->getHeight(), ResourceFormat::RGBA32Float, 1, 1, nullptr, ResourceBindFlags::Shared | ResourceBindFlags::ShaderResource | ResourceBindFlags::RenderTarget);
        pRenderContext->blit(texture->getSRV(), tex->getRTV());
        tex->captureToFile(0, 0, filename, Bitmap::FileFormat::ExrFile, Bitmap::ExportFlags::Lossless);
        break;
    }
    default:
        if (includeAlpha)
            texture->captureToFile(0, 0, filename, Bitmap::FileFormat::ExrFile, Bitmap::ExportFlags::Lossless | Bitmap::ExportFlags::ExportAlpha); // Export alpha too for specRough and diffuseOpacity
        else
            texture->captureToFile(0, 0, filename, Bitmap::FileFormat::ExrFile, Bitmap::ExportFlags::Lossless);
    }
}

void CapturePass::execute(RenderContext *pRenderContext, const RenderData &renderData)
{
    const auto frameCount = gpFramework->getGlobalClock().getFrame();
    // std::cout << "frameCount: " << frameCount << ", mCaptureCount: " << mCaptureCount << std::endl;

    for (size_t i = 0; i < mChannels.size(); ++i)
    {
        auto pTex = renderData[mChannels[i]]->asTexture();

        if (pTex && mStart)
        {
            if (mWriteTarget.empty())
            {
                if (mAccumulateSubFrames && mCountSubFrame < mAccumulateCount - 1)
                {
                }
                else
                {
                    if (frameCount >= mWriteStart && frameCount <= mWriteEnd)
                    {
                        if (!mCaptureCameraMatOnly)
                            storeTexture(pRenderContext, mCaptureCount, mChannels[i], pTex);
                        if (i == mChannels.size() - 1)
                            mCaptureCount++;
                    }
                    else if (frameCount > mWriteEnd)
                    {
                        mStart = false;
                        // gpFramework->getGlobalClock().setTime(0);
                        mCountSubFrame = 0;
                        mCaptureCount = 0;
                    }
                }
            }
            else
            {
                for (int writeTarget : mWriteTarget)
                {
                    if (frameCount == writeTarget)
                    {
                        if (!mCaptureCameraMatOnly)
                            storeTexture(pRenderContext, mCaptureCount, mChannels[i], pTex);
                        if (i == mChannels.size() - 1)
                            mCaptureCount++;
                        break;
                    }
                }
                if (frameCount == mWriteTarget.back() + 1 || frameCount > mWriteEnd)
                {
                    mStart = false;
                    // gpFramework->getGlobalClock().setTime(0);
                }
            }
        }
    }

    // Capture camera matrix
    if (mCaptureCameraMat)
    {
        mCameraMatrices.push_back(mpScene->getCamera()->getViewProjMatrixNoJitter());

        // Use less number of frames than the actual frames
        auto numFrames = mCameraMatrices.size() - 1;

        // Make matrices string
        std::string matStr, offsetStr;

        // Make matrices string
        for (size_t k = 0; k < numFrames; ++k)
        {
            const auto &mat = mCameraMatrices[k];
            matStr.append(fmt::format("    {{ // frame {}\n", k));
            for (int i = 0; i < 4; ++i)
            {
                matStr.append("        {");
                for (int j = 0; j < 4; ++j)
                {
                    matStr.append(std::to_string(mat[j][i]));
                    if (j != 3)
                        matStr.append(", ");
                }
                if (i != 3)
                    matStr.append("},\n");
                else
                    matStr.append("}\n");
            }
            if (k != numFrames - 1)
                matStr.append("    },\n");
            else
                matStr.append("    }");

            if (k != numFrames - 1)
                offsetStr.append(fmt::format("    {{0.500000, 0.500000}}, // frame {}\n", k));
            else
                offsetStr.append(fmt::format("    {{0.500000, 0.500000}} // frame {}", k));
        }

        // Write matrices
        char filename[100];
        sprintf(filename, "%s/camera_matrices.h", mDirectory.c_str());
        std::ofstream outMat(filename, std::ios_base::out);
        outMat << fmt::format(mCameraMatTemplate, numFrames, matStr, numFrames, offsetStr);
        outMat.close();
    }

    // Control
    if (mStart)
    {
        if (mAccumulateSubFrames && frameCount >= mWriteStart && frameCount <= mWriteEnd)
        {
            // Accumulate frames
            mCountSubFrame++;
            // If enough frames are accumulated, then step forwards
            if (mCountSubFrame >= mAccumulateCount)
            {
                mCountSubFrame = 0;
                // Manually step the clock
                gpFramework->getGlobalClock().step();
            }
        }
        // Skip until the starting frame
        else if (mAccumulateSubFrames && frameCount < mWriteStart)
        {
            gpFramework->getGlobalClock().step();
        }
    }
}

void CapturePass::setScene(RenderContext *pRenderContext, const Scene::SharedPtr &pScene)
{
    mpScene = pScene;

    // gpFramework->getGlobalClock().setTime(0);
    gpFramework->getGlobalClock().setFramerate(30);
    if (mExitAtEnd)
    {
        if (mWriteTarget.empty())
            gpFramework->getGlobalClock().setExitFrame(mWriteEnd + 1);
        else
            gpFramework->getGlobalClock().setExitFrame(mWriteTarget.back() + 1);
    }

    if (mAccumulateSubFrames)
    {
        // Pause and step manually
        gpFramework->getGlobalClock().pause();
    }
}

void CapturePass::renderUI(Gui::Widgets &widget)
{
    bool dirty = false;

    dirty |= widget.checkbox("Start to capture", mStart);
    widget.textbox("Directory", mDirectory);
    dirty |= widget.var("Framerate", mFramerate, 1u, 100u, 1u);
    widget.text("Number of frames");
    widget.var("start", mWriteStart, 0, 10000, 1, false);
    widget.var("end", mWriteEnd, 0, 10000, 1, false);
    // widget.var("target", mWriteTarget, -1, mWriteEnd, 1, false);
    widget.checkbox("Exit after finish", mExitAtEnd);
    dirty |= widget.checkbox("Accumulate sub frames", mAccumulateSubFrames);
    if (mAccumulateSubFrames)
        dirty |= widget.var("Number of frames to accumulate", mAccumulateCount);

    if (dirty && mExitAtEnd)
    {
        if (mWriteTarget.empty())
            gpFramework->getGlobalClock().setExitFrame(mWriteEnd + 1);
        else
            gpFramework->getGlobalClock().setExitFrame(mWriteTarget.back() + 1);
    }

    if (dirty && mAccumulateSubFrames)
    {
        // Pause and step manually
        gpFramework->getGlobalClock().pause();
    }

    if (dirty && mStart)
    {
        gpFramework->getGlobalClock().setTime(0);
        mPassChangedCB();
        logInfo("[CapturePass] mPassChangedCB is called\n");
    }
}
