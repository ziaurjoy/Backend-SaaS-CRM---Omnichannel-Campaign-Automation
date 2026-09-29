from rest_framework import serializers
from apps.campaigns.models import Campaign, CampaignRun

class CampaignSerializer(serializers.ModelSerializer):
    template_name = serializers.SerializerMethodField()
    target_collection_name = serializers.CharField(source='target_collection.name', read_only=True)

    class Meta:
        model = Campaign
        fields = '__all__'
        read_only_fields = ('id', 'business', 'created_at', 'updated_at')

    def get_template_name(self, obj):
        return obj.template.name if obj.template else None

    def validate(self, data):
        min_i = data.get('min_interval', getattr(self.instance, 'min_interval', 0) or 0)
        max_i = data.get('max_interval', getattr(self.instance, 'max_interval', 0) or 0)
        if min_i > max_i:
            raise serializers.ValidationError(
                {'max_interval': 'Maximum interval must be greater than or equal to minimum interval.'}
            )
        return data

class CampaignRunSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)

    class Meta:
        model = CampaignRun
        fields = '__all__'
        read_only_fields = ('id', 'started_at')

