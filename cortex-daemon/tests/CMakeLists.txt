# Tests
add_executable(test_inference test_inference.cpp)
target_link_libraries(test_inference PRIVATE cortex_inference)
add_test(NAME InferenceTest COMMAND test_inference)
