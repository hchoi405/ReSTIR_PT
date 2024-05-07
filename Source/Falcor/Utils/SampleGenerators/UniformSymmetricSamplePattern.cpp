#include "stdafx.h"
#include "UniformSymmetricSamplePattern.h"

namespace Falcor
{
    UniformSymmetricSamplePattern::SharedPtr UniformSymmetricSamplePattern::create(uint32_t seed, uint32_t sampleIndex)
    {
        return SharedPtr(new UniformSymmetricSamplePattern(seed, sampleIndex));
    }

    UniformSymmetricSamplePattern::UniformSymmetricSamplePattern(uint32_t seed, uint32_t sampleIndex)
    {
        mSampleIndex = sampleIndex;
        // Use the same seed for each pair of samples
        if (sampleIndex % 2 == 0)
        {
            mRng = std::mt19937(seed);
        }
        else
        {
            assert(seed > 0);
            mRng = std::mt19937(seed - 1);
        }
    }

    void UniformSymmetricSamplePattern::reset(uint32_t seed)
    {
        mRng = std::mt19937(seed);
    }

    float2 UniformSymmetricSamplePattern::next()
    {
        auto dist = std::uniform_real_distribution<float>();
        auto u = [&]()
        { return dist(mRng); };

        // (-0.5, -0.5) ~ (0.5, 0.5)
        const float2 sample = float2(u(), u()) - 0.5f;
        if (mSampleIndex % 2 == 0)
        {
            return sample;
        }
        else
        {
            // Symmetric around the origin
            return -sample;
        }
    }
}
