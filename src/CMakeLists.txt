# neverdead - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(neverdead VERSION 0.2.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

# Sources
set(NEVERDEAD_SOURCES
    src/main.cpp
    src/neverdead_diagnostics.cpp
)

if(WIN32)
    add_executable(neverdead WIN32 ${NEVERDEAD_SOURCES})
else()
    add_executable(neverdead ${NEVERDEAD_SOURCES})
endif()

rexglue_setup_target(neverdead)
add_custom_target(neverdead_runtime_dll ALL
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:rexgpu-xenos>"
        "$<TARGET_FILE_DIR:neverdead>"
    DEPENDS rexgpu-xenos
)
add_dependencies(neverdead neverdead_runtime_dll)

configure_file(neverdead.toml neverdead.toml COPYONLY)

install(TARGETS neverdead RUNTIME DESTINATION . COMPONENT Runtime)
install(FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/launcher.ps1"
    "${CMAKE_CURRENT_SOURCE_DIR}/Play.cmd"
    "$<TARGET_FILE:rexruntime>"
    "$<TARGET_FILE:rexgpu-xenos>"
    "${CMAKE_CURRENT_BINARY_DIR}/neverdead.toml"
    "${CMAKE_CURRENT_SOURCE_DIR}/../README.md"
    DESTINATION .
    COMPONENT Runtime
)

set(CPACK_GENERATOR "ZIP")
set(CPACK_PACKAGE_NAME "neverdead")
set(CPACK_PACKAGE_VERSION "${PROJECT_VERSION}-alpha")
set(CPACK_PACKAGE_FILE_NAME "neverdead-${CPACK_PACKAGE_VERSION}-windows-x64")
set(CPACK_PACKAGE_VENDOR "NeverDead Port Project")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "NeverDead native Windows x64 static recompilation port")
set(CPACK_INSTALL_CMAKE_PROJECTS "${CMAKE_BINARY_DIR};${PROJECT_NAME};Runtime;/")
include(CPack)

if(REXSDK_DIR AND EXISTS "${REXSDK_DIR}/thirdparty/imgui")
    target_include_directories(neverdead PRIVATE
        "${REXSDK_DIR}/thirdparty/imgui"
    )
endif()
