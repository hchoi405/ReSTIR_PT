from falcor import *
import os


def render_graph_ReSTIRPT(gvbuffer):
    g = RenderGraph("ReSTIRPTPass")
    loadRenderPassLibrary("AccumulatePass.dll")
    loadRenderPassLibrary("GBuffer.dll")
    loadRenderPassLibrary("ReSTIRPTPass.dll")
    loadRenderPassLibrary("ToneMapper.dll")
    loadRenderPassLibrary("ScreenSpaceReSTIRPass.dll")
    loadRenderPassLibrary("ErrorMeasurePass.dll")
    loadRenderPassLibrary("ImageLoader.dll")

    ReSTIRGIPlusPass = createPass("ReSTIRPTPass", {'samplesPerPixel': 1})
    g.addPass(ReSTIRGIPlusPass, "ReSTIRPTPass")
    GVBuffer = createPass(f"{gvbuffer}", {'samplePattern': SamplePattern.Center, 'sampleCount': 1, 'texLOD': TexLODMode.Mip0, 'useAlphaTest': True})
    g.addPass(GVBuffer, f"{gvbuffer}")
    AccumulatePass = createPass("AccumulatePass", {'enableAccumulation': False, 'precisionMode': AccumulatePrecision.Double})
    g.addPass(AccumulatePass, "AccumulatePass")
    ToneMapper = createPass("ToneMapper", {'autoExposure': False, 'exposureCompensation': 0.0, 'operator': ToneMapOp.Linear})
    g.addPass(ToneMapper, "ToneMapper")
    ScreenSpaceReSTIRPass = createPass("ScreenSpaceReSTIRPass")
    g.addPass(ScreenSpaceReSTIRPass, "ScreenSpaceReSTIRPass")

    g.addEdge(f"{gvbuffer}.vbuffer", "ReSTIRPTPass.vbuffer")
    g.addEdge(f"{gvbuffer}.mvec", "ReSTIRPTPass.motionVectors")

    g.addEdge(f"{gvbuffer}.vbuffer", "ScreenSpaceReSTIRPass.vbuffer")
    g.addEdge(f"{gvbuffer}.mvec", "ScreenSpaceReSTIRPass.motionVectors")
    g.addEdge("ScreenSpaceReSTIRPass.color", "ReSTIRPTPass.directLighting")

    g.addEdge("ReSTIRPTPass.color", "AccumulatePass.input")
    g.addEdge("AccumulatePass.output", "ToneMapper.src")

    g.markOutput("ToneMapper.dst")
    g.markOutput("AccumulatePass.output")

    return g

def add_SVGF(g, gvbuffer):
    loadRenderPassLibrary("SVGFPass.dll")
    SVGFPass = createPass("SVGFPass", {'Enabled': True, 'Iterations': 4, 'FeedbackTap': 1, 'VarianceEpsilon': 9.999999747378752e-05, 'PhiColor': 10.0, 'PhiNormal': 128.0, 'Alpha': 0.05000000074505806, 'MomentsAlpha': 0.20000000298023224})
    g.addPass(SVGFPass, "SVGFPass")
    g.addEdge("ReSTIRPTPass.color", "SVGFPass.Color")
    g.addEdge("ReSTIRPTPass.albedo", "SVGFPass.Albedo")
    g.addEdge(f"{gvbuffer}.emissive", "SVGFPass.Emission")
    g.addEdge(f"{gvbuffer}.posW", "SVGFPass.WorldPosition")
    g.addEdge(f"{gvbuffer}.normW", "SVGFPass.WorldNormal")
    g.addEdge(f"{gvbuffer}.pnFwidth", "SVGFPass.PositionNormalFwidth")
    g.addEdge(f"{gvbuffer}.linearZ", "SVGFPass.LinearZ")
    g.addEdge(f"{gvbuffer}.mvec", "SVGFPass.MotionVec")
    g.markOutput("SVGFPass.Filtered image")

    return g

gvbuffer = "GBufferRaster" # Enable SVGF
# gvbuffer = "VBufferRT"
graph_ReSTIRPT = render_graph_ReSTIRPT(gvbuffer)
if gvbuffer == "GBufferRaster":
    graph_ReSTIRPT = add_SVGF(graph_ReSTIRPT, gvbuffer)

m.addGraph(graph_ReSTIRPT)
m.loadScene('C:/Users/hchoi/repositories//ORCA/Bistro/BistroExterior2.pyscene')

m.scene.camera.nearPlane = 0.15 # Increase near plane to prevent Z-fighting in the rasterizer
