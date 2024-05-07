#pragma once
#include "CPUSampleGenerator.h"
#include <random>

namespace Falcor
{
    /** Uniform random sample pattern generator.
     */
    class dlldecl UniformSymmetricSamplePattern : public CPUSampleGenerator
    {
    public:
        using SharedPtr = std::shared_ptr<UniformSymmetricSamplePattern>;

        virtual ~UniformSymmetricSamplePattern() = default;

        static SharedPtr create(uint32_t seed = 0u, uint32_t sampleIndex = 0u);

        virtual uint32_t getSampleCount() const override { return 1; }
        virtual void reset(uint32_t seed = 0u) override;
        virtual float2 next() override;

    protected:
        UniformSymmetricSamplePattern(uint32_t seed, uint32_t sampleIndex);

        std::mt19937 mRng;
        uint32_t mSampleIndex = 0u;
    };
}
