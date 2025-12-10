import QtQuick
import QtQuick.Controls

ApplicationWindow {
    id: window
    width: 400
    height: 260
    visible: true
    title: "Qt 6 QML + C++ sample"

    Column {
        anchors.centerIn: parent
        spacing: 12

        Text {
            id: greetingText
            objectName: "greetingText"
            text: greeter.message
            font.pixelSize: 20
        }

        TextField {
            id: nameField
            objectName: "nameField"
            placeholderText: "Type your name"
            focus: true
        }

        Button {
            id: helloButton
            objectName: "helloButton"
            text: "Say hello"
            onClicked: outputLabel.text = greeter.greet(nameField.text)
        }

        Label {
            id: outputLabel
            objectName: "outputLabel"
            text: "Press the button"
            wrapMode: Text.Wrap
        }
    }
}
