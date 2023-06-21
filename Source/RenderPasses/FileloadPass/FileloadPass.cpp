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
#include "FileloadPass.h"
#include "RenderGraph/RenderPassLibrary.h"

namespace
{
    const char kDesc[] = "Fileload pass";
    const char kDirectory[] = "directory";
    const char kFilenames[] = "filenames";
    const char kChannelNames[] = "channalNames";
    const char kStartFrame[] = "startFrame";

}
namespace fs = std::filesystem;

// Don't remove this. it's required for hot-reload to function properly
extern "C" __declspec(dllexport) const char *getProjDir()
{
    return PROJECT_DIR;
}

extern "C" __declspec(dllexport) void getPasses(Falcor::RenderPassLibrary &lib)
{
    lib.registerClass("FileloadPass", kDesc, FileloadPass::create);
}

FileloadPass::SharedPtr FileloadPass::create(RenderContext *pRenderContext, const Dictionary &dict)
{
    SharedPtr pPass = SharedPtr(new FileloadPass(dict));
    return pPass;
}

FileloadPass::FileloadPass(const Dictionary &dict)
{
    // Parse the dictionary here
    for (const auto &[key, value] : dict)
    {
        if (key == kDirectory)
        {
            std::string tmp = value;
            mDirectory = tmp;
        }
        else if (key == kFilenames)
        {
            std::vector<std::string> filenames = value;
            mFilenames = filenames;
        }
        else if (key == kChannelNames)
        {
            std::vector<std::string> channelNames = value;
            mChannelNames = channelNames;
        }
        else if (key == kStartFrame)
        {
            uint32_t tmp = value;
            mStartFrame = tmp;
        }
        else
        {
            logWarning("Unknown field '" + key + "' in a FileloadPass dictionary");
        }
    }
    mLoadCount = mStartFrame;
}

std::string FileloadPass::getDesc() { return kDesc; }

Dictionary FileloadPass::getScriptingDictionary()
{
    Dictionary dict;
    dict[kDirectory] = mDirectory;
    dict[kFilenames] = mFilenames;
    dict[kChannelNames] = mChannelNames;
    dict[kStartFrame] = mStartFrame;
    return dict;
}

std::string getFilename(const std::string &channel, int frameNumber)
{
    auto frameNumberStr = std::to_string(frameNumber);
    auto frameNumberZeros = std::string(4 - std::min(4, (int)frameNumberStr.length()), '0') + frameNumberStr;
    auto filename = channel + "_" + frameNumberZeros + ".exr";
    return filename;
}

RenderPassReflection FileloadPass::reflect(const CompileData &compileData)
{
    // Define the required resources here
    RenderPassReflection reflector;
    for (size_t i = 0; i < mFilenames.size(); ++i)
    {
        std::string filename = getFilename(mFilenames[i], 0);
        auto path = fs::path(mDirectory) / fs::path(filename);
        if (fs::exists(path))
        {
            reflector.addOutput(mChannelNames[i], "").format(ResourceFormat::RGBA32Float);
        }
        else
        {
            logError("FileloadPass::reflect() - File " + path.string() + " does not exist.");
        }
    }
    mLoadCount = mStartFrame;
    return reflector;
}

void FileloadPass::execute(RenderContext *pRenderContext, const RenderData &renderData)
{
    for (size_t i = 0; i < mFilenames.size(); ++i)
    {
        const auto &filename = mFilenames[i];
        const auto &channel = mChannelNames[i];

        printf("[Frame %llu] Channel %s\n", mLoadCount, filename.c_str());
        fs::path fullpath = fs::path(mDirectory) / fs::path(getFilename(filename, (int)mLoadCount));

        // Find the full path of the specified image.
        // We retain this for later as the search paths may change during execution.
        std::string fullpath_str;
        if (findFileInDataDirectories(fullpath.string(), fullpath_str))
        {
            // Our texture is linear, so no need conversion to sRGB
            auto srcTex = Texture::createFromFile(fullpath.string(), false, false);
            auto dstTex = renderData[channel]->asTexture();

            // Blit the texture
            pRenderContext->blit(srcTex->getSRV(), dstTex->getRTV());
        }
        else
        {
            logError("Can't find image file " + fullpath.string());
            return;
        }
    }

    mLoadCount++;
}
