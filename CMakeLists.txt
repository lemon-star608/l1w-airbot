cmake_minimum_required(VERSION 3.16)

project(pico_l1w
    VERSION 0.1.0
    DESCRIPTION "PICO teleoperation receiver for GENISOM L1-W"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

find_package(Threads REQUIRED)

# The upstream repository ships prebuilt SDK archives. Define the imported
# target directly so its movement examples are not configured or built here.
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    set(PICO_L1W_SDK_ARCH "aarch64")
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
    set(PICO_L1W_SDK_ARCH "x86_64")
else()
    message(FATAL_ERROR "Unsupported architecture: ${CMAKE_SYSTEM_PROCESSOR}")
endif()

set(PICO_L1W_SDK_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/third_party/genisom_L1_sdk")
set(PICO_L1W_SDK_LIB "${PICO_L1W_SDK_ROOT}/lib/${PICO_L1W_SDK_ARCH}/libzsibot.a")

if(NOT EXISTS "${PICO_L1W_SDK_LIB}")
    message(FATAL_ERROR "Missing SDK library: ${PICO_L1W_SDK_LIB}. Run: git submodule update --init --recursive")
endif()

add_library(zsibot_sdk STATIC IMPORTED GLOBAL)
set_target_properties(zsibot_sdk PROPERTIES IMPORTED_LOCATION "${PICO_L1W_SDK_LIB}")
target_include_directories(zsibot_sdk INTERFACE "${PICO_L1W_SDK_ROOT}/include")
target_link_libraries(zsibot_sdk INTERFACE Threads::Threads)

add_executable(status_monitor src/status_monitor.cpp)
target_link_libraries(status_monitor PRIVATE zsibot_sdk)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(status_monitor PRIVATE -Wall -Wextra -Wpedantic)
endif()
