cmake_minimum_required(VERSION 3.21)

project(CPlusPlusQT6Skel VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Quick QuickControls2 Qml Test)

qt_standard_project_setup()

add_library(sample_support STATIC
    src/greeter.cpp
    src/greeter.h
)
target_include_directories(sample_support PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(sample_support PRIVATE Qt6::Qml)

qt_add_resources(sample_support "qml_resources"
    PREFIX "/qml"
    FILES
        qml/Main.qml
)

add_executable(sample_app
    src/main.cpp
)
target_link_libraries(sample_app PRIVATE sample_support Qt6::Quick Qt6::QuickControls2)
qt_import_qml_plugins(sample_app)

enable_testing()

add_executable(sample_tests
    tests/greeter_test.cpp
)
target_link_libraries(sample_tests PRIVATE sample_support Qt6::Test)
add_test(NAME greeter_tests COMMAND sample_tests)

add_executable(qml_view_tests
    tests/main_qml_test.cpp
)
target_link_libraries(qml_view_tests PRIVATE sample_support Qt6::Test Qt6::Quick Qt6::QuickControls2 Qt6::Qml)
qt_import_qml_plugins(qml_view_tests)
add_test(NAME qml_view_tests COMMAND qml_view_tests)
