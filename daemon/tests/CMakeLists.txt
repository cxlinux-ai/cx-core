# Tests CMakeLists.txt for cortexd

# Create a library with daemon sources (excluding main.cpp) for testing
set(DAEMON_TEST_SOURCES
    ${CMAKE_SOURCE_DIR}/src/core/daemon.cpp
    ${CMAKE_SOURCE_DIR}/src/config/config.cpp
    ${CMAKE_SOURCE_DIR}/src/ipc/server.cpp
    ${CMAKE_SOURCE_DIR}/src/ipc/protocol.cpp
    ${CMAKE_SOURCE_DIR}/src/ipc/handlers.cpp
    ${CMAKE_SOURCE_DIR}/src/utils/logger.cpp
)

add_library(cortexd_lib STATIC ${DAEMON_TEST_SOURCES})

target_include_directories(cortexd_lib PUBLIC
    ${CMAKE_SOURCE_DIR}/include
    ${SYSTEMD_INCLUDE_DIRS}
    ${OPENSSL_INCLUDE_DIRS}
    ${UUID_INCLUDE_DIRS}
)

target_link_libraries(cortexd_lib PUBLIC
    ${SYSTEMD_LIBRARIES}
    ${OPENSSL_LIBRARIES}
    ${UUID_LIBRARIES}
    nlohmann_json::nlohmann_json
    yaml-cpp::yaml-cpp
    pthread
)

target_compile_definitions(cortexd_lib PUBLIC
    CORTEXD_VERSION="${PROJECT_VERSION}"
)

# Unit tests
add_executable(test_config
    unit/test_config.cpp
)
target_link_libraries(test_config PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_config COMMAND test_config)

add_executable(test_protocol
    unit/test_protocol.cpp
)
target_link_libraries(test_protocol PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_protocol COMMAND test_protocol)

add_executable(test_rate_limiter
    unit/test_rate_limiter.cpp
)
target_link_libraries(test_rate_limiter PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_rate_limiter COMMAND test_rate_limiter)

add_executable(test_logger
    unit/test_logger.cpp
)
target_link_libraries(test_logger PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_logger COMMAND test_logger)

add_executable(test_common
    unit/test_common.cpp
)
target_link_libraries(test_common PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_common COMMAND test_common)

# Integration tests
add_executable(test_ipc_server
    integration/test_ipc_server.cpp
)
target_link_libraries(test_ipc_server PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_ipc_server COMMAND test_ipc_server)

add_executable(test_handlers
    integration/test_handlers.cpp
)
target_link_libraries(test_handlers PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_handlers COMMAND test_handlers)

add_executable(test_daemon
    integration/test_daemon.cpp
)
target_link_libraries(test_daemon PRIVATE cortexd_lib GTest::gtest_main)
add_test(NAME test_daemon COMMAND test_daemon)

# Add custom target to run all tests
add_custom_target(run_tests
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    DEPENDS test_config test_protocol test_rate_limiter test_logger test_common test_ipc_server test_handlers test_daemon
    COMMENT "Running all cortexd tests"
)
