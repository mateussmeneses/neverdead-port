# neverdead - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(neverdead LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

# Sources
set(NEVERDEAD_SOURCES
    src/main.cpp
)

if(WIN32)
    add_executable(neverdead WIN32 ${NEVERDEAD_SOURCES})
else()
    add_executable(neverdead ${NEVERDEAD_SOURCES})
endif()

rexglue_setup_target(neverdead)

if(REXSDK_DIR AND EXISTS "${REXSDK_DIR}/thirdparty/imgui")
    target_include_directories(neverdead PRIVATE
        "${REXSDK_DIR}/thirdparty/imgui"
    )
endif()
