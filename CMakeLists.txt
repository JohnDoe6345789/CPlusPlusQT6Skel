cmake_minimum_required(VERSION 3.21)

project(CPlusPlusQT6Skel VERSION 0.1 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Quick QuickControls2 Qml Test)

qt_standard_project_setup()

option(BUILD_PDCURSES_WINCON "Build the WinCon flavor of PDCursesMod (static library)" ON)
set(PDCURSES_MOD_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/third_party/PDCursesMod")

if(BUILD_PDCURSES_WINCON AND WIN32 AND EXISTS "${PDCURSES_MOD_ROOT}/curses.h")
    file(GLOB PDCURSES_CORE_SOURCES CONFIGURE_DEPENDS
        "${PDCURSES_MOD_ROOT}/pdcurses/*.c"
    )

    set(PDCURSES_WINCON_SOURCES
        "${PDCURSES_MOD_ROOT}/wincon/pdcclip.c"
        "${PDCURSES_MOD_ROOT}/wincon/pdcdisp.c"
        "${PDCURSES_MOD_ROOT}/wincon/pdcgetsc.c"
        "${PDCURSES_MOD_ROOT}/wincon/pdckbd.c"
        "${PDCURSES_MOD_ROOT}/wincon/pdcscrn.c"
        "${PDCURSES_MOD_ROOT}/wincon/pdcsetsc.c"
        "${PDCURSES_MOD_ROOT}/wincon/pdcutil.c"
    )

    add_library(pdcursesmod STATIC
        ${PDCURSES_CORE_SOURCES}
        ${PDCURSES_WINCON_SOURCES}
    )
    add_library(PDCursesMod::pdcurses ALIAS pdcursesmod)

    target_include_directories(pdcursesmod PUBLIC
        ${PDCURSES_MOD_ROOT}
        ${PDCURSES_MOD_ROOT}/wincon
    )

    if(MSVC)
        target_compile_definitions(pdcursesmod PRIVATE _CRT_SECURE_NO_WARNINGS)
    endif()

    # Match the upstream WinCon build's default link dependencies.
    target_link_libraries(pdcursesmod PUBLIC
        gdi32
        winspool
        shell32
        ole32
        comdlg32
        advapi32
        winmm
    )
elseif(BUILD_PDCURSES_WINCON)
    message(WARNING "PDCursesMod sources not found or unsupported platform; skipping WinCon build.")
endif()

add_library(sample_support STATIC
    src/greeter.cpp
    src/greeter.h
)
target_include_directories(sample_support PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(sample_support PRIVATE Qt6::Qml)

if(TARGET PDCursesMod::pdcurses)
    add_library(qml_curses STATIC
        src/qml_curses_frontend.cpp
        src/qml_curses_frontend.h
        src/qml_parser.cpp
        src/qml_parser.h
    )
    target_include_directories(qml_curses PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
    target_link_libraries(qml_curses PUBLIC PDCursesMod::pdcurses)
else()
    message(WARNING "PDCursesMod target is unavailable; skipping qml_curses frontend build.")
endif()

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

if(TARGET qml_curses)
    add_executable(qml_curses_tests
        tests/qml_curses_frontend_test.cpp
        tests/qml_parser_test.cpp
    )
    target_link_libraries(qml_curses_tests PRIVATE qml_curses Qt6::Test)
    add_test(NAME qml_curses_tests COMMAND qml_curses_tests)
endif()
