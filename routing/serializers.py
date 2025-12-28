from rest_framework import serializers


class PlanRequestSerializer(serializers.Serializer):
    start = serializers.CharField(required=True, allow_blank=False)
    end = serializers.CharField(required=True, allow_blank=False)

    def validate(self, data):
        start = data.get("start", "").strip()
        end = data.get("end", "").strip()

        if start.lower() == end.lower():
            raise serializers.ValidationError("start and end cannot be the same location")

        data["start"] = start
        data["end"] = end
        return data

